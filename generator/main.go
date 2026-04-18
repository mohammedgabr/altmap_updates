package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// FlexTags handles both string and slice tags in YAML
type FlexTags []string

func (f *FlexTags) UnmarshalYAML(value *yaml.Node) error {
	var s string
	if err := value.Decode(&s); err == nil {
		parts := strings.Split(s, ",")
		for _, p := range parts {
			trimmed := strings.TrimSpace(p)
			if trimmed != "" {
				*f = append(*f, trimmed)
			}
		}
		return nil
	}
	var sl []string
	if err := value.Decode(&sl); err == nil {
		*f = sl
		return nil
	}
	return nil
}

// Template represents the partial structure of a Nuclei YAML template
type Template struct {
	ID   string `yaml:"id"`
	Info struct {
		Name           string         `yaml:"name"`
		Severity       string         `yaml:"severity"`
		Description    string         `yaml:"description"`
		Tags           FlexTags       `yaml:"tags"`
		Classification map[string]any `yaml:"classification"`
	} `yaml:"info"`
}

// CVSEntry is the schema for cves.json (JSONLines)
type CVSEntry struct {
	ID       string `json:"ID"`
	Info     any    `json:"Info"`
	FilePath string `json:"file_path"`
}

func main() {
	startTime := time.Now()

	// Paths
	upstreamRoot := "../upstream"
	verifiedCSVPath := "../verified.csv"
	unverifiedCSVPath := "../unverified.csv"
	changedCSVPath := "../changed_after_verified.csv"
	cvesJsonPath := "../cves.json"
	checksumPath := "../cves.json-checksum.txt"
	tagsIndexPath := "../tags-index.json"
	verifiedRoot := "../altmap_verified"
	changedVerifiedRoot := filepath.Join(verifiedRoot, "changed")

	// 1. Load Verified templates from CSV
	verifiedMap := make(map[string]string) // ID -> relative path
	vFile, err := os.Open(verifiedCSVPath)
	if err == nil {
		reader := csv.NewReader(vFile)
		records, _ := reader.ReadAll()
		for _, row := range records {
			if len(row) >= 2 {
				verifiedMap[row[0]] = row[1]
			}
		}
		vFile.Close()
	}

	// 2. Data structures for output
	var cveEntries []CVSEntry
	var unverifiedList [][]string
	var changedList [][]string
	tagMap := make(map[string][]string)

	// 3. Walk upstream/http to find all available templates
	filepath.Walk(upstreamRoot, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".yaml") {
			return nil
		}

		// Calculate relative path (e.g., http/cves/...)
		relPath, _ := filepath.Rel(upstreamRoot, path)

		// Determine the source of truth for this template
		var templateData []byte
		var finalFilePath string
		
		isVerified := false
		if _, ok := verifiedMap[relPath]; ok { // Use path as key to be precise
			isVerified = true
		}

		// Priority 1: User-Edited Version
		changedPath := filepath.Join(changedVerifiedRoot, relPath)
		if _, err := os.Stat(changedPath); err == nil {
			templateData, _ = os.ReadFile(changedPath)
			finalFilePath = filepath.Join("altmap_verified/changed", relPath)
		} else {
			// Priority 2: Upstream Version
			templateData, _ = os.ReadFile(path)
			finalFilePath = filepath.Join("upstream", relPath)
		}

		var t Template
		if err := yaml.Unmarshal(templateData, &t); err != nil {
			fmt.Printf("Warning: Failed to parse %s: %v\n", finalFilePath, err)
			return nil
		}
		
		if !isVerified {
			unverifiedList = append(unverifiedList, []string{t.ID, relPath})
			t.Info.Name = "[unverified] " + t.Info.Name
		} else {
			// Change detection: compare upstream vs verified snapshot
			checkUpstreamChanges(path, relPath, verifiedRoot, &changedList, t.ID)
		}

		// Prepare Info object for JSON
		infoObj := map[string]any{
			"Name":           t.Info.Name,
			"Severity":       t.Info.Severity,
			"Description":    t.Info.Description,
			"Tags":           strings.Join(t.Info.Tags, ","),
			"Classification": t.Info.Classification,
		}

		// Create CVSEntry
		entry := CVSEntry{
			ID:       t.ID,
			Info:     infoObj,
			FilePath: finalFilePath,
		}
		cveEntries = append(cveEntries, entry)

		// Populate tags for tagMap
		for _, tag := range t.Info.Tags {
			if tag != "" {
				tagMap[tag] = append(tagMap[tag], finalFilePath)
			}
		}

		return nil
	})

	// 4. Write cves.json (JSONLines format)
	f, _ := os.Create(cvesJsonPath)
	bw := bufio.NewWriter(f)
	for _, entry := range cveEntries {
		jsonData, _ := json.Marshal(entry)
		bw.Write(jsonData)
		bw.WriteString("\n")
	}
	bw.Flush()
	f.Close()

	// 5. Generate Checksum
	genChecksum(cvesJsonPath, checksumPath)

	// 6. Write unverified.csv
	writeCSV(unverifiedCSVPath, unverifiedList)

	// 7. Write changed_after_verified.csv
	writeCSV(changedCSVPath, changedList)

	// 8. Write tags-index.json
	tagsOutput := map[string]any{
		"scope":        "http",
		"generated_at": time.Now().UTC().Format(time.RFC3339),
		"tags":         tagMap,
	}
	tagsJson, _ := json.MarshalIndent(tagsOutput, "", "  ")
	os.WriteFile(tagsIndexPath, tagsJson, 0644)

	fmt.Printf("Done in %v. Processed %d templates.\n", time.Since(startTime), len(cveEntries))
}

func checkUpstreamChanges(upstreamPath, relPath, verifiedRoot string, changedList *[][]string, id string) {
	// Look for a reference copy in altmap_verified
	verifiedSnapshotPath := filepath.Join(verifiedRoot, relPath)
	
	// If it doesn't exist, we don't have a baseline to compare against
	if _, err := os.Stat(verifiedSnapshotPath); os.IsNotExist(err) {
		return
	}

	// Compare file contents
	uData, _ := os.ReadFile(upstreamPath)
	vData, _ := os.ReadFile(verifiedSnapshotPath)

	if !bytes.Equal(uData, vData) {
		*changedList = append(*changedList, []string{id, relPath})
	}
}

func genChecksum(filePath, outputPath string) {
	f, _ := os.Open(filePath)
	defer f.Close()
	h := sha256.New()
	io.Copy(h, f)
	os.WriteFile(outputPath, []byte(fmt.Sprintf("%x", h.Sum(nil))), 0644)
}

func writeCSV(path string, data [][]string) {
	f, _ := os.Create(path)
	defer f.Close()
	w := csv.NewWriter(f)
	w.WriteAll(data)
}

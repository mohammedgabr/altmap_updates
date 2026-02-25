package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

type Template struct {
	Info struct {
		Tags string `yaml:"tags"`
	} `yaml:"info"`
}

func main() {
	tagMap := make(map[string][]string)

	root := "nuclei-templates/http"

	filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() || !strings.HasSuffix(path, ".yaml") {
			return nil
		}

		data, err := os.ReadFile(path)
		if err != nil {
			return nil
		}

		var t Template
		if err := yaml.Unmarshal(data, &t); err != nil {
			return nil
		}

		relPath := strings.TrimPrefix(path, "nuclei-templates/")

		for _, tag := range strings.Split(t.Info.Tags, ",") {
			tag = strings.TrimSpace(tag)
			if tag != "" {
				tagMap[tag] = append(tagMap[tag], relPath)
			}
		}
		return nil
	})

	output := map[string]any{
		"scope":        "http",
		"generated_at": time.Now().UTC().Format(time.RFC3339),
		"tags":         tagMap,
	}

	jsonData, _ := json.MarshalIndent(output, "", "  ")
	_ = os.WriteFile("tags-index.json", jsonData, 0644)
}
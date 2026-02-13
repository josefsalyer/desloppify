package main

import (
	"encoding/json"
	"fmt"
	"os"
)

// ExtractResult holds the combined extraction results from one or more Go source files.
type ExtractResult struct {
	Functions  []FunctionInfo  `json:"functions"`
	Structs    []StructInfo    `json:"structs"`
	Interfaces []InterfaceInfo `json:"interfaces"`
}

// FunctionInfo describes a function or method extracted from Go source.
type FunctionInfo struct {
	Name     string   `json:"name"`
	File     string   `json:"file"`
	Line     int      `json:"line"`
	EndLine  int      `json:"end_line"`
	LOC      int      `json:"loc"`
	Body     string   `json:"body"`
	Params   []string `json:"params"`
	Receiver string   `json:"receiver,omitempty"`
	Exported bool     `json:"exported"`
}

// StructInfo describes a struct type extracted from Go source.
type StructInfo struct {
	Name     string   `json:"name"`
	File     string   `json:"file"`
	Line     int      `json:"line"`
	LOC      int      `json:"loc"`
	Methods  []string `json:"methods"`
	Fields   []string `json:"fields"`
	Embedded []string `json:"embedded"`
	Exported bool     `json:"exported"`
}

// InterfaceInfo describes an interface type extracted from Go source.
type InterfaceInfo struct {
	Name    string   `json:"name"`
	File    string   `json:"file"`
	Line    int      `json:"line"`
	Methods []string `json:"methods"`
}

func main() {
	args := os.Args[1:]
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "Usage: go-extract <file1.go> [file2.go ...]")
		os.Exit(1)
	}

	combined := &ExtractResult{
		Functions:  []FunctionInfo{},
		Structs:    []StructInfo{},
		Interfaces: []InterfaceInfo{},
	}

	for _, arg := range args {
		result, err := extractFile(arg)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warning: %s: %v\n", arg, err)
			continue
		}
		combined.Functions = append(combined.Functions, result.Functions...)
		combined.Structs = append(combined.Structs, result.Structs...)
		combined.Interfaces = append(combined.Interfaces, result.Interfaces...)
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(combined); err != nil {
		fmt.Fprintf(os.Stderr, "error encoding JSON: %v\n", err)
		os.Exit(1)
	}
}

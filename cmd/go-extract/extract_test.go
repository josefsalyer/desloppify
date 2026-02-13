package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestExtractFunctions(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "main.go")
	os.WriteFile(src, []byte(`package main

func Hello(name string) string {
	return "Hello, " + name
}

func (s *Server) Start(ctx context.Context) error {
	return nil
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 2 {
		t.Fatalf("expected 2 functions, got %d", len(result.Functions))
	}
	if result.Functions[0].Name != "Hello" {
		t.Errorf("expected Hello, got %s", result.Functions[0].Name)
	}
	if result.Functions[0].Exported != true {
		t.Errorf("expected Hello to be exported")
	}
	if len(result.Functions[0].Params) != 1 {
		t.Errorf("expected 1 param for Hello, got %d", len(result.Functions[0].Params))
	}
	if len(result.Functions[0].Params) > 0 && result.Functions[0].Params[0] != "name" {
		t.Errorf("expected param 'name', got %s", result.Functions[0].Params[0])
	}
	if result.Functions[0].LOC < 3 {
		t.Errorf("expected LOC >= 3 for Hello, got %d", result.Functions[0].LOC)
	}
	if result.Functions[0].Body == "" {
		t.Errorf("expected non-empty body for Hello")
	}
	if result.Functions[1].Name != "Start" {
		t.Errorf("expected Start, got %s", result.Functions[1].Name)
	}
	if result.Functions[1].Receiver != "Server" {
		t.Errorf("expected receiver Server, got %s", result.Functions[1].Receiver)
	}
}

func TestExtractStructs(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "types.go")
	os.WriteFile(src, []byte(`package main

type User struct {
	Name  string
	Email string
}

type Admin struct {
	User
	Role string
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Structs) != 2 {
		t.Fatalf("expected 2 structs, got %d", len(result.Structs))
	}
	if result.Structs[0].Name != "User" {
		t.Errorf("expected User, got %s", result.Structs[0].Name)
	}
	if len(result.Structs[0].Fields) != 2 {
		t.Errorf("expected 2 fields, got %d", len(result.Structs[0].Fields))
	}
	if result.Structs[0].Exported != true {
		t.Errorf("expected User to be exported")
	}
	if result.Structs[1].Name != "Admin" {
		t.Errorf("expected Admin, got %s", result.Structs[1].Name)
	}
	if len(result.Structs[1].Embedded) != 1 {
		t.Errorf("expected 1 embedded type for Admin, got %d", len(result.Structs[1].Embedded))
	}
	if len(result.Structs[1].Embedded) > 0 && result.Structs[1].Embedded[0] != "User" {
		t.Errorf("expected embedded type 'User', got %s", result.Structs[1].Embedded[0])
	}
	if len(result.Structs[1].Fields) != 1 {
		t.Errorf("expected 1 field for Admin, got %d", len(result.Structs[1].Fields))
	}
}

func TestExtractInterfaces(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "iface.go")
	os.WriteFile(src, []byte(`package main

type Reader interface {
	Read(p []byte) (n int, err error)
	Close() error
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Interfaces) != 1 {
		t.Fatalf("expected 1 interface, got %d", len(result.Interfaces))
	}
	if result.Interfaces[0].Name != "Reader" {
		t.Errorf("expected Reader, got %s", result.Interfaces[0].Name)
	}
	if len(result.Interfaces[0].Methods) != 2 {
		t.Errorf("expected 2 methods, got %d", len(result.Interfaces[0].Methods))
	}
	if len(result.Interfaces[0].Methods) > 0 && result.Interfaces[0].Methods[0] != "Read" {
		t.Errorf("expected method 'Read', got %s", result.Interfaces[0].Methods[0])
	}
	if len(result.Interfaces[0].Methods) > 1 && result.Interfaces[0].Methods[1] != "Close" {
		t.Errorf("expected method 'Close', got %s", result.Interfaces[0].Methods[1])
	}
}

func TestExtractMethodsAttachedToStruct(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "server.go")
	os.WriteFile(src, []byte(`package main

type Server struct {
	Host string
	Port int
}

func (s *Server) Start() error {
	return nil
}

func (s Server) Addr() string {
	return s.Host
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Structs) != 1 {
		t.Fatalf("expected 1 struct, got %d", len(result.Structs))
	}
	if len(result.Structs[0].Methods) != 2 {
		t.Errorf("expected 2 methods on Server, got %d", len(result.Structs[0].Methods))
	}
}

func TestExtractUnexportedNames(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "private.go")
	os.WriteFile(src, []byte(`package main

func helper() {}

type config struct {
	value string
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 1 {
		t.Fatalf("expected 1 function, got %d", len(result.Functions))
	}
	if result.Functions[0].Exported {
		t.Errorf("expected helper to be unexported")
	}
	if len(result.Structs) != 1 {
		t.Fatalf("expected 1 struct, got %d", len(result.Structs))
	}
	if result.Structs[0].Exported {
		t.Errorf("expected config to be unexported")
	}
}

func TestExtractEmptyFile(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "empty.go")
	os.WriteFile(src, []byte(`package main
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 0 {
		t.Errorf("expected 0 functions, got %d", len(result.Functions))
	}
	if len(result.Structs) != 0 {
		t.Errorf("expected 0 structs, got %d", len(result.Structs))
	}
	if len(result.Interfaces) != 0 {
		t.Errorf("expected 0 interfaces, got %d", len(result.Interfaces))
	}
}

func TestExtractFileNotFound(t *testing.T) {
	_, err := extractFile("/nonexistent/file.go")
	if err == nil {
		t.Fatalf("expected error for nonexistent file")
	}
}

func TestExtractMultipleParamsAndReturns(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "multi.go")
	os.WriteFile(src, []byte(`package main

func Process(a int, b string, c bool) (string, error) {
	return "", nil
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 1 {
		t.Fatalf("expected 1 function, got %d", len(result.Functions))
	}
	if len(result.Functions[0].Params) != 3 {
		t.Errorf("expected 3 params, got %d", len(result.Functions[0].Params))
	}
	expectedParams := []string{"a", "b", "c"}
	for i, expected := range expectedParams {
		if i < len(result.Functions[0].Params) && result.Functions[0].Params[i] != expected {
			t.Errorf("expected param %d to be %s, got %s", i, expected, result.Functions[0].Params[i])
		}
	}
}

func TestExtractLineNumbers(t *testing.T) {
	dir := t.TempDir()
	src := filepath.Join(dir, "lines.go")
	os.WriteFile(src, []byte(`package main

// Comment
func First() {
}

func Second() {
	x := 1
	_ = x
}
`), 0644)

	result, err := extractFile(src)
	if err != nil {
		t.Fatalf("extractFile failed: %v", err)
	}
	if len(result.Functions) != 2 {
		t.Fatalf("expected 2 functions, got %d", len(result.Functions))
	}
	// First starts at line 4
	if result.Functions[0].Line != 4 {
		t.Errorf("expected First at line 4, got %d", result.Functions[0].Line)
	}
	// Second starts at line 7
	if result.Functions[1].Line != 7 {
		t.Errorf("expected Second at line 7, got %d", result.Functions[1].Line)
	}
	if result.Functions[1].EndLine != 10 {
		t.Errorf("expected Second end at line 10, got %d", result.Functions[1].EndLine)
	}
}

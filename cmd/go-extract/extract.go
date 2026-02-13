package main

import (
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"unicode"
)

// extractFile parses a Go source file and extracts functions, structs, and interfaces.
func extractFile(filename string) (*ExtractResult, error) {
	srcBytes, err := os.ReadFile(filename)
	if err != nil {
		return nil, fmt.Errorf("reading file: %w", err)
	}
	src := string(srcBytes)

	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, filename, srcBytes, parser.ParseComments)
	if err != nil {
		return nil, fmt.Errorf("parsing file: %w", err)
	}

	result := &ExtractResult{
		Functions:  []FunctionInfo{},
		Structs:    []StructInfo{},
		Interfaces: []InterfaceInfo{},
	}

	// Track methods by receiver type name so we can attach them to structs.
	methodsByReceiver := make(map[string][]string)

	ast.Inspect(file, func(n ast.Node) bool {
		switch node := n.(type) {
		case *ast.FuncDecl:
			fi := extractFunction(fset, node, filename, src)
			result.Functions = append(result.Functions, fi)
			if fi.Receiver != "" {
				methodsByReceiver[fi.Receiver] = append(methodsByReceiver[fi.Receiver], fi.Name)
			}

		case *ast.GenDecl:
			if node.Tok != token.TYPE {
				return true
			}
			for _, spec := range node.Specs {
				ts, ok := spec.(*ast.TypeSpec)
				if !ok {
					continue
				}
				switch t := ts.Type.(type) {
				case *ast.StructType:
					si := extractStruct(fset, ts, t, filename)
					result.Structs = append(result.Structs, si)
				case *ast.InterfaceType:
					ii := extractInterface(fset, ts, t, filename)
					result.Interfaces = append(result.Interfaces, ii)
				}
			}
		}
		return true
	})

	// Attach methods to their receiver structs.
	for i, s := range result.Structs {
		if methods, ok := methodsByReceiver[s.Name]; ok {
			result.Structs[i].Methods = methods
		}
	}

	return result, nil
}

// extractFunction extracts information from a function declaration.
func extractFunction(fset *token.FileSet, fn *ast.FuncDecl, filename, src string) FunctionInfo {
	startPos := fset.Position(fn.Pos())
	endPos := fset.Position(fn.End())

	loc := endPos.Line - startPos.Line + 1

	// Extract body text from source bytes.
	body := ""
	if fn.Body != nil {
		bodyStart := fset.Position(fn.Body.Pos())
		bodyEnd := fset.Position(fn.Body.End())
		if bodyStart.Offset >= 0 && bodyEnd.Offset <= len(src) {
			body = src[bodyStart.Offset:bodyEnd.Offset]
		}
	}

	// Extract parameter names.
	params := extractParams(fn.Type.Params)

	// Extract receiver type name.
	receiver := ""
	if fn.Recv != nil && len(fn.Recv.List) > 0 {
		receiver = receiverTypeName(fn.Recv.List[0].Type)
	}

	name := fn.Name.Name
	exported := isExported(name)

	return FunctionInfo{
		Name:     name,
		File:     filename,
		Line:     startPos.Line,
		EndLine:  endPos.Line,
		LOC:      loc,
		Body:     body,
		Params:   params,
		Receiver: receiver,
		Exported: exported,
	}
}

// extractParams extracts parameter names from a field list.
func extractParams(fields *ast.FieldList) []string {
	if fields == nil {
		return []string{}
	}
	var params []string
	for _, field := range fields.List {
		for _, name := range field.Names {
			params = append(params, name.Name)
		}
		// If a field has no names (bare type like in interface method signatures),
		// we skip it as specified.
	}
	if params == nil {
		return []string{}
	}
	return params
}

// receiverTypeName extracts the type name from a receiver expression,
// handling both value and pointer receivers.
func receiverTypeName(expr ast.Expr) string {
	switch t := expr.(type) {
	case *ast.StarExpr:
		return receiverTypeName(t.X)
	case *ast.Ident:
		return t.Name
	case *ast.IndexExpr:
		// Generic type: T[P]
		return receiverTypeName(t.X)
	default:
		return ""
	}
}

// extractStruct extracts information from a struct type declaration.
func extractStruct(fset *token.FileSet, ts *ast.TypeSpec, st *ast.StructType, filename string) StructInfo {
	startPos := fset.Position(ts.Pos())
	endPos := fset.Position(st.End())
	loc := endPos.Line - startPos.Line + 1

	var fields []string
	var embedded []string

	if st.Fields != nil {
		for _, field := range st.Fields.List {
			if len(field.Names) == 0 {
				// Embedded type.
				embedded = append(embedded, typeString(field.Type))
			} else {
				for _, name := range field.Names {
					fields = append(fields, name.Name)
				}
			}
		}
	}

	if fields == nil {
		fields = []string{}
	}
	if embedded == nil {
		embedded = []string{}
	}

	name := ts.Name.Name
	return StructInfo{
		Name:     name,
		File:     filename,
		Line:     startPos.Line,
		LOC:      loc,
		Methods:  []string{},
		Fields:   fields,
		Embedded: embedded,
		Exported: isExported(name),
	}
}

// extractInterface extracts information from an interface type declaration.
func extractInterface(fset *token.FileSet, ts *ast.TypeSpec, it *ast.InterfaceType, filename string) InterfaceInfo {
	startPos := fset.Position(ts.Pos())

	var methods []string
	if it.Methods != nil {
		for _, method := range it.Methods.List {
			for _, name := range method.Names {
				methods = append(methods, name.Name)
			}
		}
	}
	if methods == nil {
		methods = []string{}
	}

	return InterfaceInfo{
		Name:    ts.Name.Name,
		File:    filename,
		Line:    startPos.Line,
		Methods: methods,
	}
}

// typeString returns a string representation of an AST type expression.
func typeString(expr ast.Expr) string {
	switch t := expr.(type) {
	case *ast.Ident:
		return t.Name
	case *ast.StarExpr:
		return "*" + typeString(t.X)
	case *ast.SelectorExpr:
		return typeString(t.X) + "." + t.Sel.Name
	case *ast.ArrayType:
		return "[]" + typeString(t.Elt)
	case *ast.MapType:
		return "map[" + typeString(t.Key) + "]" + typeString(t.Value)
	case *ast.InterfaceType:
		return "interface{}"
	case *ast.IndexExpr:
		return typeString(t.X) + "[" + typeString(t.Index) + "]"
	default:
		return fmt.Sprintf("%T", expr)
	}
}

// isExported checks whether a name is exported (starts with an uppercase letter).
func isExported(name string) bool {
	if name == "" {
		return false
	}
	r := []rune(name)
	return unicode.IsUpper(r[0])
}


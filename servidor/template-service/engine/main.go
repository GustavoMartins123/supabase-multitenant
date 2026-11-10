package main

import (
	"bytes"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io"
	"os"
	"strings"
	"text/template/parse"
	"unicode/utf8"
)

const maxBody = 1024 * 1024

//go:embed defaults/*.html
var defaults embed.FS

var kinds = []string{"confirmation", "invite", "magic_link", "recovery", "email_change", "reauthentication"}

type input struct {
	Kind string `json:"kind"`
	Body string `json:"body"`
}

type limitedBuffer struct{ bytes.Buffer }

func (b *limitedBuffer) Write(p []byte) (int, error) {
	if b.Len()+len(p) > 2*maxBody {
		return 0, errors.New("a prévia excede 2 MB")
	}
	return b.Buffer.Write(p)
}

// Inspect executable nodes, excluding comments and quoted strings. A field in
// `with .Data` is metadata, not a root GoTrue variable. `$` always denotes root.
func rootPipe(pipe *parse.PipeNode, root bool) bool {
	if pipe == nil {
		return false
	}
	arg := pipe.String()
	return (arg == "." && root) || arg == "$"
}

func requiredFields(t *template.Template) map[string]bool {
	found, seen := map[string]bool{}, map[string]bool{}
	var visit func(parse.Node, bool)
	var walk func(string, bool)
	walk = func(name string, root bool) {
		key := fmt.Sprintf("%s:%t", name, root)
		if seen[key] {
			return
		}
		seen[key] = true
		part := t.Lookup(name)
		if part != nil && part.Tree != nil {
			visit(part.Tree.Root, root)
		}
	}
	visit = func(node parse.Node, root bool) {
		if node == nil {
			return
		}
		switch n := node.(type) {
		case *parse.ListNode:
			if n != nil {
				for _, child := range n.Nodes {
					visit(child, root)
				}
			}
		case *parse.ActionNode:
			visit(n.Pipe, root)
		case *parse.PipeNode:
			if n != nil {
				for _, cmd := range n.Cmds {
					visit(cmd, root)
				}
			}
		case *parse.CommandNode:
			for _, arg := range n.Args {
				visit(arg, root)
			}
		case *parse.FieldNode:
			if root && len(n.Ident) > 0 {
				found[n.Ident[0]] = true
			}
		case *parse.VariableNode:
			if len(n.Ident) > 1 && n.Ident[0] == "$" {
				found[n.Ident[1]] = true
			}
		case *parse.IfNode:
			visit(n.Pipe, root)
			visit(n.List, root)
			visit(n.ElseList, root)
		case *parse.WithNode:
			visit(n.Pipe, root)
			visit(n.List, rootPipe(n.Pipe, root))
			visit(n.ElseList, root)
		case *parse.RangeNode:
			visit(n.Pipe, root)
			visit(n.List, false)
			visit(n.ElseList, root)
		case *parse.TemplateNode:
			visit(n.Pipe, root)
			walk(n.Name, rootPipe(n.Pipe, root))
		case *parse.ChainNode:
			visit(n.Node, root)
		}
	}
	// An unused define cannot satisfy the required authentication variable.
	walk("email", true)
	return found
}

func render(in input) (string, error) {
	known := false
	for _, kind := range kinds {
		if kind == in.Kind {
			known = true
		}
	}
	if !known {
		return "", errors.New("tipo de template desconhecido")
	}
	if !utf8.ValidString(in.Body) || strings.IndexByte(in.Body, 0) >= 0 {
		return "", errors.New("o HTML deve ser UTF-8 sem bytes nulos")
	}
	if len(in.Body) == 0 || len(in.Body) > maxBody {
		return "", errors.New("o HTML deve conter entre 1 byte e 1 MB")
	}
	t, err := template.New("email").Parse(in.Body)
	if err != nil {
		return "", fmt.Errorf("Go template inválido: %w", err)
	}
	found := requiredFields(t)
	valid := found["Token"] || found["ConfirmationURL"] || found["TokenHash"]
	if in.Kind == "reauthentication" {
		valid = found["Token"]
	}
	if !valid {
		return "", errors.New("inclua .Token, .ConfirmationURL ou .TokenHash (reautenticação exige .Token)")
	}
	data := map[string]any{
		"Email": "pessoa@example.com", "NewEmail": "novo@example.com", "SendingTo": "pessoa@example.com", "Token": "123456",
		"TokenHash": "hash-de-exemplo", "ConfirmationURL": "https://example.com/auth/v1/verify?token=exemplo&type=" + in.Kind,
		"SiteURL": "https://example.com", "RedirectTo": "https://example.com/acesso",
		"Data": map[string]any{"name": "Pessoa de exemplo", "full_name": "Pessoa de exemplo"},
	}
	var output limitedBuffer
	if err := t.Execute(&output, data); err != nil {
		return "", fmt.Errorf("erro ao renderizar Go template: %w", err)
	}
	return output.String(), nil
}

func main() {
	if len(os.Args) == 2 && os.Args[1] == "defaults" {
		result := map[string]string{}
		for _, kind := range kinds {
			body, err := defaults.ReadFile("defaults/" + kind + ".html")
			if err != nil {
				panic(err)
			}
			result[kind] = string(body)
		}
		json.NewEncoder(os.Stdout).Encode(result)
		return
	}
	raw, err := io.ReadAll(io.LimitReader(os.Stdin, 8*maxBody+1))
	if err == nil && (!utf8.Valid(raw) || len(raw) > 8*maxBody) {
		err = errors.New("entrada inválida ou excessiva")
	}
	var in input
	if err == nil {
		err = json.Unmarshal(raw, &in)
	}
	var html string
	if err == nil {
		html, err = render(in)
	}
	if err != nil {
		json.NewEncoder(os.Stdout).Encode(map[string]string{"error": err.Error()})
		os.Exit(1)
	}
	json.NewEncoder(os.Stdout).Encode(map[string]string{"html": html})
}

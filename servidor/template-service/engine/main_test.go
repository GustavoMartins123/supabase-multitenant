package main

import (
	"strings"
	"testing"
)

func TestEmbeddedDefaults(t *testing.T) {
	for _, kind := range kinds {
		body, err := defaults.ReadFile("defaults/" + kind + ".html")
		if err != nil {
			t.Fatal(err)
		}
		if _, err := render(input{kind, string(body)}); err != nil {
			t.Fatalf("%s: %v", kind, err)
		}
	}
}

func TestInvalidTemplates(t *testing.T) {
	for _, body := range []string{
		"", "<h1>Sem código</h1>", "{{ .Token", "{{ unknown .Token }}",
		"{{/* .Token */}}", "{{ ` .Token ` }}", "{{ with .Data }}{{ .Token }}{{ end }}",
		"{{ define `unused` }}{{ .Token }}{{ end }}Sem código",
		"{{ define `metadata` }}{{ .Token }}{{ end }}{{ with .Data }}{{ template `metadata` . }}{{ end }}",
		strings.Repeat("á", maxBody/2+1), string([]byte{0xff, 0xfe}), "{{ .Token }}\x00",
	} {
		if _, err := render(input{"magic_link", body}); err == nil {
			t.Errorf("accepted %q", body[:min(len(body), 100)])
		}
	}
	if _, err := render(input{"unknown", "{{ .Token }}"}); err == nil {
		t.Fatal("unknown kind accepted")
	}
	if _, err := render(input{"reauthentication", "{{ .ConfirmationURL }}"}); err == nil {
		t.Fatal("reauthentication needs a code")
	}
}

func TestGoTemplateExecutionAndEscaping(t *testing.T) {
	for _, body := range []string{
		"{{ .Token }}", "{{ $.Token }}", "{{ with . }}{{ .Token }}{{ end }}", "{{ .ConfirmationURL }}", "{{ .TokenHash }}",
		"{{ $code := .Token }}<b>{{ $code }}</b>",
		"{{ define `code` }}{{ .Token }}{{ end }}{{ template `code` . }}",
	} {
		if _, err := render(input{"magic_link", body}); err != nil {
			t.Errorf("%q: %v", body, err)
		}
	}
	html, err := render(input{"invite", "{{ .Token }}<a href='{{ .ConfirmationURL }}'>{{ .Email }}</a>"})
	if err != nil || !strings.Contains(html, "123456") || !strings.Contains(html, "&amp;type=invite") {
		t.Fatalf("unexpected preview: %q %v", html, err)
	}
}

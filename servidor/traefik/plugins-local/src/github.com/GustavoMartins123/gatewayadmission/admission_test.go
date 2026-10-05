package gatewayadmission

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type roundTrip func(*http.Request) (*http.Response, error)

func (f roundTrip) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

func middleware(t *testing.T, next http.Handler) *Middleware {
	t.Helper()
	h, err := New(context.Background(), next, &Config{EvaluatorURL: "http://key-authorizer:18010/v1/admit",
		Secret: strings.Repeat("a", 64), TrustedProxyCIDRs: []string{"10.0.0.1/32"}}, "test")
	if err != nil {
		t.Fatal(err)
	}
	return h.(*Middleware)
}

func TestInvalidProxyNetworks(t *testing.T) {
	for _, value := range []string{"0.0.0.0/0", "::/0", "::ffff:0:0/96", "::ffff:192.0.2.0/120", "192.0.2.1/24", ""} {
		_, err := New(context.Background(), http.NotFoundHandler(), &Config{
			EvaluatorURL: "http://key-authorizer:18010/v1/admit",
			Secret:       strings.Repeat("a", 64), TrustedProxyCIDRs: []string{value}}, "test")
		if err == nil {
			t.Fatalf("invalid proxy network accepted: %q", value)
		}
	}
}

func TestProxyChain(t *testing.T) {
	m := middleware(t, http.NotFoundHandler())
	for _, tc := range []struct {
		peer, chain, want string
		invalid           bool
	}{
		{"10.0.0.2:12", "8.8.8.8", "10.0.0.2", false},
		{"10.0.0.1:12", "8.8.8.8", "8.8.8.8", false},
		{"10.0.0.1:12", "8.8.8.8, 200.160.2.3", "200.160.2.3", false},
		{"10.0.0.1:12", "", "", true},
		{"10.0.0.1:12", "bad, 8.8.8.8", "", true},
		{"10.0.0.1:12", "::ffff:8.8.8.8", "8.8.8.8", false},
	} {
		r := httptest.NewRequest("GET", "/", nil)
		r.RemoteAddr = tc.peer
		r.Header.Set("X-Forwarded-For", tc.chain)
		got, err := m.clientIP(r)
		if (err != nil) != tc.invalid || got != tc.want {
			t.Fatalf("%+v: %q %v", tc, got, err)
		}
	}
}

func TestScrubbingAndStatus(t *testing.T) {
	called := false
	m := middleware(t, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		called = true
		if r.Header.Get("X-Gateway-Admission") != strings.Repeat("b", 43) || r.Header.Get("X-Country-Code") != "" || r.Header.Get("X-Opaque-Key-Id") != "" {
			t.Fatal("unsafe identity headers")
		}
		w.WriteHeader(200)
	}))
	m.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatal(err)
		}
		if body["client_ip"] != "200.160.2.3" || body["uri"] != "/abc?q=1" {
			t.Fatal("metadata mismatch")
		}
		return &http.Response{StatusCode: 204, Header: http.Header{"X-Gateway-Admission": {strings.Repeat("b", 43)}}, Body: io.NopCloser(strings.NewReader(""))}, nil
	})
	r := httptest.NewRequest("POST", "/abc?q=1", nil)
	r.RemoteAddr = "10.0.0.1:12"
	r.Header.Set("X-Forwarded-For", "8.8.8.8, 200.160.2.3")
	for _, h := range []string{"X-Gateway-Admission", "X-Country-Code", "X-Opaque-Key-Id"} {
		r.Header.Set(h, "forged")
	}
	w := httptest.NewRecorder()
	m.ServeHTTP(w, r)
	if !called || w.Code != 200 {
		t.Fatal(w.Code)
	}
	called = false
	m.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 429, Header: http.Header{"Retry-After": {"60"}}, Body: io.NopCloser(strings.NewReader(`{"error":"quota","message":"exhausted"}`))}, nil
	})
	w = httptest.NewRecorder()
	m.ServeHTTP(w, r)
	if called || w.Code != 429 || w.Header().Get("Retry-After") != "60" {
		t.Fatal("quota status lost")
	}
	m.client.Transport = roundTrip(func(r *http.Request) (*http.Response, error) {
		return &http.Response{StatusCode: 429, Header: make(http.Header), Body: io.NopCloser(strings.NewReader(`{}`))}, nil
	})
	w = httptest.NewRecorder()
	m.ServeHTTP(w, r)
	if called || w.Code != 503 {
		t.Fatal("invalid protocol accepted")
	}
}

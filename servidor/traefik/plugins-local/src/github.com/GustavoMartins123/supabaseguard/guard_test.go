package supabaseguard

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

type mutableClock struct {
	now time.Time
}

func (c *mutableClock) Now() time.Time {
	return c.now
}

func newTestGuard(t *testing.T, next http.Handler, config *Config, clock *mutableClock) *Guard {
	t.Helper()
	handler, err := New(context.Background(), next, config, "test")
	if err != nil {
		t.Fatal(err)
	}
	guard := handler.(*Guard)
	guard.now = clock.Now
	return guard
}

func request(t *testing.T, handler http.Handler, method string, path string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, "http://example.test"+path, nil)
	req.RemoteAddr = "203.0.113.10:40000"
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, req)
	return recorder
}

func TestProjectProfileNeverCountsSuccess(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
	config := CreateConfig()
	config.Mode = "enforce"
	config.Scope = "project-a"
	guard := newTestGuard(t, next, config, clock)

	for i := 0; i < 30; i++ {
		response := request(t, guard, http.MethodPost, "/project-a/auth/v1/token")
		if response.Code != http.StatusOK {
			t.Fatalf("request %d returned %d", i, response.Code)
		}
	}
}

func TestProjectProfileNeverCountsServerErrors(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	config := CreateConfig()
	config.Mode = "enforce"
	config.Scope = "project-a"
	guard := newTestGuard(t, next, config, clock)

	for i := 0; i < 30; i++ {
		response := request(t, guard, http.MethodPost, "/project-a/auth/v1/token")
		if response.Code != http.StatusInternalServerError {
			t.Fatalf("request %d returned %d", i, response.Code)
		}
	}
}

func TestNormalNotFoundDoesNotCount(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	})
	config := CreateConfig()
	config.Mode = "enforce"
	config.Scope = "project-a"
	guard := newTestGuard(t, next, config, clock)

	for i := 0; i < 30; i++ {
		response := request(t, guard, http.MethodGet, "/project-a/rest/v1/missing")
		if response.Code != http.StatusNotFound {
			t.Fatalf("request %d returned %d", i, response.Code)
		}
	}
}

func TestScannerPathBansOnlyAfterConfiguredFailures(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/project-a/.env" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	config := CreateConfig()
	config.Mode = "enforce"
	config.Scope = "project-a"
	guard := newTestGuard(t, next, config, clock)

	for i := 0; i < 2; i++ {
		response := request(t, guard, http.MethodGet, "/project-a/.env")
		if response.Code != http.StatusNotFound {
			t.Fatalf("scanner request %d returned %d", i, response.Code)
		}
	}
	blocked := request(t, guard, http.MethodGet, "/project-a/rest/v1/table")
	if blocked.Code != http.StatusTooManyRequests {
		t.Fatalf("expected 429, got %d", blocked.Code)
	}
}

func TestAuthFailuresAreScopedPerProjectInstance(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	failure := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
	})
	success := http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	configA := CreateConfig()
	configA.Mode = "enforce"
	configA.Scope = "project-a"
	configA.AuthThreshold = 3
	guardA := newTestGuard(t, failure, configA, clock)

	configB := CreateConfig()
	configB.Mode = "enforce"
	configB.Scope = "project-b"
	configB.AuthThreshold = 3
	guardB := newTestGuard(t, success, configB, clock)

	for i := 0; i < 3; i++ {
		response := request(t, guardA, http.MethodPost, "/project-a/auth/v1/token")
		if response.Code != http.StatusBadRequest {
			t.Fatalf("failure request %d returned %d", i, response.Code)
		}
	}

	blocked := request(t, guardA, http.MethodGet, "/project-a/rest/v1/table")
	if blocked.Code != http.StatusTooManyRequests {
		t.Fatalf("expected project A to be blocked, got %d", blocked.Code)
	}

	allowed := request(t, guardB, http.MethodGet, "/project-b/rest/v1/table")
	if allowed.Code != http.StatusOK {
		t.Fatalf("expected project B to remain allowed, got %d", allowed.Code)
	}
}

func TestBanExpiresWithoutBeingExtendedByBlockedRequests(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/project-a/.env" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	config := CreateConfig()
	config.Mode = "enforce"
	config.Scope = "project-a"
	config.ScannerBanTime = "10m"
	guard := newTestGuard(t, next, config, clock)

	request(t, guard, http.MethodGet, "/project-a/.env")
	request(t, guard, http.MethodGet, "/project-a/.env")
	if response := request(t, guard, http.MethodGet, "/project-a/rest/v1/table"); response.Code != http.StatusTooManyRequests {
		t.Fatalf("expected initial ban, got %d", response.Code)
	}

	clock.now = clock.now.Add(9 * time.Minute)
	if response := request(t, guard, http.MethodGet, "/project-a/rest/v1/table"); response.Code != http.StatusTooManyRequests {
		t.Fatalf("expected ban before expiry, got %d", response.Code)
	}

	clock.now = clock.now.Add(2 * time.Minute)
	if response := request(t, guard, http.MethodGet, "/project-a/rest/v1/table"); response.Code != http.StatusOK {
		t.Fatalf("expected ban to expire, got %d", response.Code)
	}
}

func TestObserveModeNeverBlocks(t *testing.T) {
	clock := &mutableClock{now: time.Date(2026, 7, 12, 12, 0, 0, 0, time.UTC)}
	next := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/project-a/.env" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		w.WriteHeader(http.StatusOK)
	})
	config := CreateConfig()
	config.Mode = "observe"
	config.Scope = "project-a"
	guard := newTestGuard(t, next, config, clock)

	request(t, guard, http.MethodGet, "/project-a/.env")
	request(t, guard, http.MethodGet, "/project-a/.env")
	for i := 0; i < 5; i++ {
		response := request(t, guard, http.MethodGet, "/project-a/rest/v1/table")
		if response.Code != http.StatusOK {
			t.Fatalf("observe request %d returned %d", i, response.Code)
		}
	}
}

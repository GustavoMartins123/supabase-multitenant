package supabaseguard

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"
)

type Config struct {
	Mode              string   `yaml:"mode,omitempty"`
	Profile           string   `yaml:"profile,omitempty"`
	Scope             string   `yaml:"scope,omitempty"`
	ClientIPHeader    string   `yaml:"clientIPHeader,omitempty"`
	TrustedProxyCIDRs []string `yaml:"trustedProxyCIDRs,omitempty"`
	Allowlist         []string `yaml:"allowlist,omitempty"`
	MaxTrackedClients int      `yaml:"maxTrackedClients,omitempty"`
	CleanupInterval   string   `yaml:"cleanupInterval,omitempty"`
	AuthThreshold     int      `yaml:"authThreshold,omitempty"`
	AuthWindow        string   `yaml:"authWindow,omitempty"`
	AuthBanTime       string   `yaml:"authBanTime,omitempty"`
	ScannerThreshold  int      `yaml:"scannerThreshold,omitempty"`
	ScannerWindow     string   `yaml:"scannerWindow,omitempty"`
	ScannerBanTime    string   `yaml:"scannerBanTime,omitempty"`
	LogMatches        bool     `yaml:"logMatches,omitempty"`
}

func CreateConfig() *Config {
	return &Config{
		Mode:              "observe",
		Profile:           "project",
		MaxTrackedClients: 10000,
		CleanupInterval:   "5m",
		AuthThreshold:     12,
		AuthWindow:        "10m",
		AuthBanTime:       "15m",
		ScannerThreshold:  2,
		ScannerWindow:     "2m",
		ScannerBanTime:    "1h",
	}
}

type event struct {
	at     time.Time
	weight int
}

type clientState struct {
	events      []event
	bannedUntil time.Time
	lastSeen    time.Time
}

type statusRange struct {
	from int
	to   int
}

type policy struct {
	name      string
	path      *regexp.Regexp
	methods   map[string]struct{}
	statuses  []statusRange
	threshold int
	weight    int
	window    time.Duration
	banTime   time.Duration
}

type Guard struct {
	next              http.Handler
	name              string
	mode              string
	profile           string
	scope             string
	clientIPHeader    string
	trustedProxyCIDRs []*net.IPNet
	allowlist         []*net.IPNet
	maxTrackedClients int
	cleanupInterval   time.Duration
	logMatches        bool
	policies          []policy
	mu                sync.Mutex
	states            map[string]*clientState
	lastCleanup       time.Time
	now               func() time.Time
}

func New(_ context.Context, next http.Handler, config *Config, name string) (http.Handler, error) {
	if next == nil {
		return nil, errors.New("next handler ausente")
	}
	if config == nil {
		config = CreateConfig()
	}

	mode := strings.ToLower(strings.TrimSpace(config.Mode))
	if mode == "" {
		mode = "observe"
	}
	if mode != "observe" && mode != "enforce" {
		return nil, fmt.Errorf("mode invalido: %s", config.Mode)
	}

	profile := strings.ToLower(strings.TrimSpace(config.Profile))
	if profile == "" {
		profile = "project"
	}
	if profile != "project" && profile != "malicious" {
		return nil, fmt.Errorf("profile invalido: %s", config.Profile)
	}

	scope := strings.TrimSpace(config.Scope)
	if scope == "" {
		if profile == "project" {
			return nil, errors.New("scope obrigatorio para profile project")
		}
		scope = "global-malicious"
	}

	cleanupInterval, err := parseDuration(config.CleanupInterval, "5m")
	if err != nil {
		return nil, fmt.Errorf("cleanupInterval invalido: %w", err)
	}

	allowlist, err := parseCIDRs(config.Allowlist)
	if err != nil {
		return nil, fmt.Errorf("allowlist invalida: %w", err)
	}
	trustedProxyCIDRs, err := parseCIDRs(config.TrustedProxyCIDRs)
	if err != nil {
		return nil, fmt.Errorf("trustedProxyCIDRs invalido: %w", err)
	}

	policies, err := buildPolicies(profile, config)
	if err != nil {
		return nil, err
	}

	maxTrackedClients := config.MaxTrackedClients
	if maxTrackedClients <= 0 {
		maxTrackedClients = 10000
	}

	return &Guard{
		next:              next,
		name:              name,
		mode:              mode,
		profile:           profile,
		scope:             scope,
		clientIPHeader:    strings.TrimSpace(config.ClientIPHeader),
		trustedProxyCIDRs: trustedProxyCIDRs,
		allowlist:         allowlist,
		maxTrackedClients: maxTrackedClients,
		cleanupInterval:   cleanupInterval,
		logMatches:        config.LogMatches,
		policies:          policies,
		states:            make(map[string]*clientState),
		now:               time.Now,
	}, nil
}

func buildPolicies(profile string, config *Config) ([]policy, error) {
	scannerPath, err := regexp.Compile(`(?i)(^|/)(?:\.env[^/]*|\.git(?:/|$)|\.svn(?:/|$)|\.hg(?:/|$)|\.bzr(?:/|$)|\.htaccess(?:$|[/?])|\.htpasswd(?:$|[/?])|wp-admin(?:/|$)|wp-login\.php(?:$|[/?])|phpmyadmin(?:/|$)|pma(?:/|$)|cgi-bin(?:/|$)|server-status(?:$|[/?])|xmlrpc\.php(?:$|[/?])|actuator(?:/|$)|debug/pprof(?:/|$)|global-protect(?:/|$)|ssl-vpn(?:/|$)|owa/auth(?:/|$)|getcfg\.php(?:$|[/?])|aws\.sh(?:$|[/?])|vb\.env(?:$|[/?])|env\.py(?:$|[/?]))`)
	if err != nil {
		return nil, err
	}

	scannerWindow, err := parseDuration(config.ScannerWindow, "2m")
	if err != nil {
		return nil, fmt.Errorf("scannerWindow invalido: %w", err)
	}
	scannerBanTime, err := parseDuration(config.ScannerBanTime, "1h")
	if err != nil {
		return nil, fmt.Errorf("scannerBanTime invalido: %w", err)
	}
	scannerThreshold := config.ScannerThreshold
	if scannerThreshold <= 0 {
		scannerThreshold = 2
	}
	scannerStatuses, err := parseStatusRanges("400-499")
	if err != nil {
		return nil, err
	}

	policies := []policy{
		{
			name:      "scanner-path",
			path:      scannerPath,
			statuses:  scannerStatuses,
			threshold: scannerThreshold,
			weight:    1,
			window:    scannerWindow,
			banTime:   scannerBanTime,
		},
	}

	if profile == "malicious" {
		return policies, nil
	}

	authPath, err := regexp.Compile(`(?i)(^|/)auth/v1/(token|verify|recover)/?$`)
	if err != nil {
		return nil, err
	}
	authWindow, err := parseDuration(config.AuthWindow, "10m")
	if err != nil {
		return nil, fmt.Errorf("authWindow invalido: %w", err)
	}
	authBanTime, err := parseDuration(config.AuthBanTime, "15m")
	if err != nil {
		return nil, fmt.Errorf("authBanTime invalido: %w", err)
	}
	authThreshold := config.AuthThreshold
	if authThreshold <= 0 {
		authThreshold = 12
	}
	authStatuses, err := parseStatusRanges("400,401,403,429")
	if err != nil {
		return nil, err
	}
	policies = append(policies, policy{
		name:      "auth-failure",
		path:      authPath,
		methods:   map[string]struct{}{http.MethodPost: {}},
		statuses:  authStatuses,
		threshold: authThreshold,
		weight:    1,
		window:    authWindow,
		banTime:   authBanTime,
	})

	return policies, nil
}

func parseDuration(value string, fallback string) (time.Duration, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		value = fallback
	}
	return time.ParseDuration(value)
}

func parseCIDRs(values []string) ([]*net.IPNet, error) {
	result := make([]*net.IPNet, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if !strings.Contains(value, "/") {
			ip := net.ParseIP(value)
			if ip == nil {
				return nil, fmt.Errorf("IP invalido: %s", value)
			}
			if ip.To4() != nil {
				value += "/32"
			} else {
				value += "/128"
			}
		}
		_, network, err := net.ParseCIDR(value)
		if err != nil {
			return nil, err
		}
		result = append(result, network)
	}
	return result, nil
}

func parseStatusRanges(spec string) ([]statusRange, error) {
	parts := strings.Split(spec, ",")
	ranges := make([]statusRange, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		bounds := strings.SplitN(part, "-", 2)
		from, err := strconv.Atoi(strings.TrimSpace(bounds[0]))
		if err != nil || from < 100 || from > 599 {
			return nil, fmt.Errorf("status invalido: %s", part)
		}
		to := from
		if len(bounds) == 2 {
			to, err = strconv.Atoi(strings.TrimSpace(bounds[1]))
			if err != nil || to < from || to > 599 {
				return nil, fmt.Errorf("intervalo de status invalido: %s", part)
			}
		}
		ranges = append(ranges, statusRange{from: from, to: to})
	}
	return ranges, nil
}

func (g *Guard) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	now := g.now()
	ip := g.clientIP(r)
	if ip == "" || g.isAllowlisted(ip) {
		g.next.ServeHTTP(w, r)
		return
	}

	if until, rule, banned := g.activeBan(ip, now); banned {
		if g.mode == "enforce" {
			g.log("blocked", ip, rule, 0, 0, until)
			writeBlocked(w, until.Sub(now))
			return
		}
	}

	recorder := &statusWriter{ResponseWriter: w}
	g.next.ServeHTTP(recorder, r)
	status := recorder.statusCode()

	for _, p := range g.policies {
		if !p.matches(r, status) {
			continue
		}
		score, bannedUntil, newlyBanned := g.record(ip, p, now)
		if g.logMatches {
			g.log("matched", ip, p.name, status, score, bannedUntil)
		}
		if newlyBanned {
			action := "ban_scheduled"
			if g.mode == "observe" {
				action = "would_ban"
			}
			g.log(action, ip, p.name, status, score, bannedUntil)
		}
	}
}

func (p policy) matches(r *http.Request, status int) bool {
	if len(p.methods) > 0 {
		if _, ok := p.methods[strings.ToUpper(r.Method)]; !ok {
			return false
		}
	}
	if !p.path.MatchString(r.URL.Path) {
		return false
	}
	for _, item := range p.statuses {
		if status >= item.from && status <= item.to {
			return true
		}
	}
	return false
}

func (g *Guard) record(ip string, p policy, now time.Time) (int, time.Time, bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.cleanupLocked(now)

	key := stateKey(ip, p.name)
	state := g.states[key]
	if state == nil {
		g.ensureCapacityLocked(now)
		state = &clientState{}
		g.states[key] = state
	}
	state.lastSeen = now

	if now.Before(state.bannedUntil) {
		return scoreEvents(state.events), state.bannedUntil, false
	}
	if !state.bannedUntil.IsZero() {
		state.bannedUntil = time.Time{}
		state.events = nil
	}

	cutoff := now.Add(-p.window)
	kept := state.events[:0]
	for _, item := range state.events {
		if !item.at.Before(cutoff) {
			kept = append(kept, item)
		}
	}
	state.events = append(kept, event{at: now, weight: p.weight})
	score := scoreEvents(state.events)
	if score < p.threshold {
		return score, time.Time{}, false
	}

	state.bannedUntil = now.Add(p.banTime)
	return score, state.bannedUntil, true
}

func (g *Guard) activeBan(ip string, now time.Time) (time.Time, string, bool) {
	g.mu.Lock()
	defer g.mu.Unlock()
	g.cleanupLocked(now)

	var latest time.Time
	var rule string
	for _, p := range g.policies {
		state := g.states[stateKey(ip, p.name)]
		if state == nil {
			continue
		}
		state.lastSeen = now
		if now.Before(state.bannedUntil) && state.bannedUntil.After(latest) {
			latest = state.bannedUntil
			rule = p.name
		}
	}
	return latest, rule, !latest.IsZero()
}

func (g *Guard) cleanupLocked(now time.Time) {
	if !g.lastCleanup.IsZero() && now.Sub(g.lastCleanup) < g.cleanupInterval {
		return
	}
	g.lastCleanup = now
	retention := 2 * time.Hour
	for _, p := range g.policies {
		candidate := p.window + p.banTime
		if candidate > retention {
			retention = candidate
		}
	}
	for key, state := range g.states {
		if now.Before(state.bannedUntil) {
			continue
		}
		if state.lastSeen.IsZero() || now.Sub(state.lastSeen) > retention {
			delete(g.states, key)
		}
	}
}

func (g *Guard) ensureCapacityLocked(now time.Time) {
	if len(g.states) < g.maxTrackedClients {
		return
	}
	var oldestKey string
	var oldest time.Time
	for key, state := range g.states {
		if now.Before(state.bannedUntil) {
			continue
		}
		if oldestKey == "" || state.lastSeen.Before(oldest) {
			oldestKey = key
			oldest = state.lastSeen
		}
	}
	if oldestKey != "" {
		delete(g.states, oldestKey)
		return
	}
	for key := range g.states {
		delete(g.states, key)
		break
	}
}

func scoreEvents(events []event) int {
	total := 0
	for _, item := range events {
		total += item.weight
	}
	return total
}

func stateKey(ip string, rule string) string {
	return ip + "\x00" + rule
}

func (g *Guard) clientIP(r *http.Request) string {
	peer := parseIP(r.RemoteAddr)
	if g.clientIPHeader == "" || peer == nil || !containsIP(g.trustedProxyCIDRs, peer) {
		if peer == nil {
			return ""
		}
		return peer.String()
	}

	value := r.Header.Get(g.clientIPHeader)
	for _, item := range strings.Split(value, ",") {
		ip := net.ParseIP(strings.TrimSpace(item))
		if ip != nil {
			return ip.String()
		}
	}
	return peer.String()
}

func parseIP(value string) net.IP {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil
	}
	if host, _, err := net.SplitHostPort(value); err == nil {
		return net.ParseIP(strings.Trim(host, "[]"))
	}
	return net.ParseIP(strings.Trim(value, "[]"))
}

func containsIP(networks []*net.IPNet, ip net.IP) bool {
	for _, network := range networks {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func (g *Guard) isAllowlisted(value string) bool {
	ip := net.ParseIP(value)
	return ip != nil && containsIP(g.allowlist, ip)
}

func (g *Guard) log(action string, ip string, rule string, status int, score int, until time.Time) {
	untilValue := ""
	if !until.IsZero() {
		untilValue = until.UTC().Format(time.RFC3339)
	}
	fmt.Fprintf(
		os.Stdout,
		"{\"level\":\"info\",\"plugin\":\"supabaseguard\",\"name\":%q,\"action\":%q,\"scope\":%q,\"profile\":%q,\"client_ip\":%q,\"rule\":%q,\"status\":%d,\"score\":%d,\"banned_until\":%q}\n",
		g.name,
		action,
		g.scope,
		g.profile,
		ip,
		rule,
		status,
		score,
		untilValue,
	)
}

func writeBlocked(w http.ResponseWriter, remaining time.Duration) {
	seconds := int64(remaining / time.Second)
	if remaining%time.Second != 0 {
		seconds++
	}
	if seconds < 1 {
		seconds = 1
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Retry-After", strconv.FormatInt(seconds, 10))
	w.WriteHeader(http.StatusTooManyRequests)
	_, _ = w.Write([]byte(`{"message":"too many abusive requests"}`))
}

type statusWriter struct {
	http.ResponseWriter
	status int
}

func (w *statusWriter) statusCode() int {
	if w.status == 0 {
		return http.StatusOK
	}
	return w.status
}

func (w *statusWriter) WriteHeader(status int) {
	if w.status != 0 {
		return
	}
	w.status = status
	w.ResponseWriter.WriteHeader(status)
}

func (w *statusWriter) Write(body []byte) (int, error) {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}
	return w.ResponseWriter.Write(body)
}

func (w *statusWriter) Flush() {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}
	if flusher, ok := w.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func (w *statusWriter) Hijack() (net.Conn, *bufio.ReadWriter, error) {
	hijacker, ok := w.ResponseWriter.(http.Hijacker)
	if !ok {
		return nil, nil, errors.New("response writer nao suporta hijack")
	}
	return hijacker.Hijack()
}

func (w *statusWriter) Push(target string, options *http.PushOptions) error {
	pusher, ok := w.ResponseWriter.(http.Pusher)
	if !ok {
		return http.ErrNotSupported
	}
	return pusher.Push(target, options)
}

func (w *statusWriter) ReadFrom(reader io.Reader) (int64, error) {
	if w.status == 0 {
		w.WriteHeader(http.StatusOK)
	}
	if readerFrom, ok := w.ResponseWriter.(io.ReaderFrom); ok {
		return readerFrom.ReadFrom(reader)
	}
	return io.Copy(struct{ io.Writer }{w.ResponseWriter}, reader)
}

func (w *statusWriter) CloseNotify() <-chan bool {
	if notifier, ok := w.ResponseWriter.(http.CloseNotifier); ok {
		return notifier.CloseNotify()
	}
	channel := make(chan bool)
	return channel
}

func (w *statusWriter) Unwrap() http.ResponseWriter {
	return w.ResponseWriter
}

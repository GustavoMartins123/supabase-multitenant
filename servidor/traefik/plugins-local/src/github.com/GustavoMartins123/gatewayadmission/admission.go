package gatewayadmission

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type Config struct {
	EvaluatorURL      string   `yaml:"evaluatorURL"`
	Secret            string   `yaml:"secret"`
	ProjectRef        string   `yaml:"projectRef"`
	GatewayToken      string   `yaml:"gatewayToken"`
	TrustedProxyCIDRs []string `yaml:"trustedProxyCIDRs"`
}

func CreateConfig() *Config { return &Config{} }

type Middleware struct {
	next    http.Handler
	config  Config
	client  *http.Client
	proxies []*net.IPNet
}

func New(_ context.Context, next http.Handler, config *Config, _ string) (http.Handler, error) {
	if next == nil || config == nil || len(config.Secret) != 64 {
		return nil, errors.New("admission configuration missing")
	}
	if _, err := hex.DecodeString(config.Secret); err != nil || config.Secret != strings.ToLower(config.Secret) {
		return nil, errors.New("invalid admission secret")
	}
	target, err := url.Parse(config.EvaluatorURL)
	if err != nil || target.Scheme != "http" || target.Host != "key-authorizer:18010" || target.Path != "/v1/admit" || target.RawQuery != "" {
		return nil, errors.New("invalid admission evaluator")
	}
	m := &Middleware{next: next, config: *config, client: &http.Client{Timeout: 4 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}}
	for _, value := range config.TrustedProxyCIDRs {
		address, network, err := net.ParseCIDR(value)
		if err != nil {
			return nil, err
		}
		ones, bits := network.Mask.Size()
		if !address.Equal(network.IP) || (bits == 128 && address.To4() != nil) {
			return nil, errors.New("proxy network must use canonical IPv4 or IPv6 notation")
		}
		if ones == 0 {
			return nil, errors.New("unrestricted proxy trust denied")
		}
		m.proxies = append(m.proxies, network)
	}
	return m, nil
}

func (m *Middleware) trusted(ip net.IP) bool {
	for _, network := range m.proxies {
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func (m *Middleware) clientIP(r *http.Request) (string, error) {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return "", err
	}
	peer := net.ParseIP(host)
	if peer == nil {
		return "", errors.New("invalid peer")
	}
	if !m.trusted(peer) {
		return peer.String(), nil
	}
	chain := r.Header.Values("X-Forwarded-For")
	if len(chain) != 1 || chain[0] == "" {
		return "", errors.New("trusted proxy chain missing")
	}
	hops := strings.Split(chain[0], ",")
	if len(hops) > 32 {
		return "", errors.New("proxy chain too long")
	}
	addresses := make([]net.IP, len(hops))
	for i, value := range hops {
		addresses[i] = net.ParseIP(strings.TrimSpace(value))
		if addresses[i] == nil {
			return "", errors.New("invalid forwarded address")
		}
	}
	for i := len(addresses) - 1; i >= 0; i-- {
		if !m.trusted(peer) {
			break
		}
		peer = addresses[i]
	}
	return peer.String(), nil
}

func deny(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]string{"error": "admission_unavailable", "message": message})
}

func (m *Middleware) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		deny(w, 503, "Request identity unavailable")
		return
	}
	requestID := hex.EncodeToString(random)
	w.Header().Set("X-Request-ID", requestID)
	w.Header().Set("Access-Control-Expose-Headers", "Retry-After, X-Request-ID")
	r.Header.Set("X-Request-ID", requestID)
	ip, err := m.clientIP(r)
	for key := range r.Header {
		low := strings.ToLower(key)
		if strings.HasPrefix(low, "x-gateway-") || strings.HasPrefix(low, "x-admission-") ||
			strings.HasPrefix(low, "x-opaque-") || low == "x-api-key-id" || low == "x-country-code" ||
			low == "x-project-gateway-token" || low == "x-project-ref" || low == "x-project-name" {
			r.Header.Del(key)
		}
	}
	if err != nil {
		deny(w, 403, "Client origin could not be verified")
		return
	}
	keys := r.Header.Values("Apikey")
	auth := r.Header.Values("Authorization")
	if len(keys) > 1 || len(auth) > 1 {
		deny(w, 403, "Ambiguous application credentials")
		return
	}
	uri := r.URL.RequestURI()
	if len(uri) > 32768 {
		deny(w, 414, "Request URI too long")
		return
	}
	payload, err := json.Marshal(map[string]string{
		"project_ref": m.config.ProjectRef, "gateway_token": m.config.GatewayToken, "uri": uri,
		"method": r.Method, "client_ip": ip, "api_key": r.Header.Get("Apikey"), "authorization": r.Header.Get("Authorization"),
	})
	if err != nil {
		deny(w, 503, "Admission metadata unavailable")
		return
	}
	request, err := http.NewRequestWithContext(r.Context(), http.MethodPost, m.config.EvaluatorURL, bytes.NewReader(payload))
	if err != nil {
		deny(w, 503, "Admission request unavailable")
		return
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Admission-Secret", m.config.Secret)
	response, err := m.client.Do(request)
	if err != nil {
		deny(w, 503, "Admission evaluator unavailable")
		return
	}
	defer response.Body.Close()
	if response.StatusCode != 204 {
		data, err := io.ReadAll(io.LimitReader(response.Body, 65537))
		var body map[string]interface{}
		if err != nil || len(data) > 65536 || json.Unmarshal(data, &body) != nil || response.StatusCode < 400 || response.StatusCode > 599 {
			deny(w, 503, "Invalid admission protocol")
			return
		}
		code, codeOK := body["error"].(string)
		message, messageOK := body["message"].(string)
		if !codeOK || !messageOK || code == "" || message == "" {
			deny(w, 503, "Invalid admission error")
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		if retry := response.Header.Get("Retry-After"); retry != "" {
			w.Header().Set("Retry-After", retry)
		}
		w.WriteHeader(response.StatusCode)
		_, _ = w.Write(data)
		return
	}
	if r.Method == "OPTIONS" {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Authorization, Content-Type, apikey, X-Client-Info, X-Supabase-Auth, x-supabase-api-version, tus-resumable, upload-length, upload-metadata, upload-offset, x-upsert")
		w.Header().Set("Cache-Control", "no-store")
		w.WriteHeader(204)
		return
	}
	ticket := response.Header.Get("X-Gateway-Admission")
	if len(ticket) != 43 {
		deny(w, 503, "Admission ticket missing")
		return
	}
	r.Header.Set("X-Gateway-Admission", ticket)
	r.Header.Set("X-Admission-URI", uri)
	r.Header.Set("X-Admission-Method", r.Method)
	r.Header.Set("X-Admission-Origin-IP", ip)
	m.next.ServeHTTP(w, r)
}

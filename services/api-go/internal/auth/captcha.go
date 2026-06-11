package auth

import (
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"html"
	"math/big"
	"strings"
	"sync"
	"time"
)

const captchaAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

type CaptchaConfig struct {
	TTL        time.Duration
	CodeLength int
}

type CaptchaChallenge struct {
	ID        string    `json:"captcha_id"`
	ImageData string    `json:"image"`
	ExpiresAt time.Time `json:"expires_at"`
}

type captchaRecord struct {
	Answer    string
	ExpiresAt time.Time
}

type CaptchaStore struct {
	mu      sync.Mutex
	ttl     time.Duration
	length  int
	records map[string]captchaRecord
}

func NewCaptchaStore(config CaptchaConfig) *CaptchaStore {
	ttl := config.TTL
	if ttl <= 0 {
		ttl = 3 * time.Minute
	}
	length := config.CodeLength
	if length <= 0 {
		length = 5
	}

	return &CaptchaStore{
		ttl:     ttl,
		length:  length,
		records: map[string]captchaRecord{},
	}
}

func (s *CaptchaStore) NewChallenge() (CaptchaChallenge, error) {
	id, err := randomToken(18)
	if err != nil {
		return CaptchaChallenge{}, err
	}
	code, err := randomCode(s.length, captchaAlphabet)
	if err != nil {
		return CaptchaChallenge{}, err
	}
	svg, err := renderCaptchaSVG(code)
	if err != nil {
		return CaptchaChallenge{}, err
	}

	now := time.Now().UTC()
	expiresAt := now.Add(s.ttl)

	s.mu.Lock()
	defer s.mu.Unlock()
	s.cleanupLocked(now)
	s.records[id] = captchaRecord{Answer: code, ExpiresAt: expiresAt}

	return CaptchaChallenge{
		ID:        id,
		ImageData: "data:image/svg+xml;base64," + base64.StdEncoding.EncodeToString([]byte(svg)),
		ExpiresAt: expiresAt,
	}, nil
}

func (s *CaptchaStore) Verify(id string, answer string) bool {
	id = strings.TrimSpace(id)
	answer = normalizeCaptchaAnswer(answer)
	if id == "" || answer == "" {
		return false
	}

	now := time.Now().UTC()

	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.records[id]
	if !ok {
		return false
	}
	delete(s.records, id)
	if now.After(record.ExpiresAt) {
		return false
	}

	expected := normalizeCaptchaAnswer(record.Answer)
	return subtle.ConstantTimeCompare([]byte(expected), []byte(answer)) == 1
}

func (s *CaptchaStore) cleanupLocked(now time.Time) {
	for id, record := range s.records {
		if now.After(record.ExpiresAt) {
			delete(s.records, id)
		}
	}
}

func normalizeCaptchaAnswer(answer string) string {
	return strings.ToUpper(strings.TrimSpace(answer))
}

func randomToken(byteLength int) (string, error) {
	bytes := make([]byte, byteLength)
	if _, err := rand.Read(bytes); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(bytes), nil
}

func randomCode(length int, alphabet string) (string, error) {
	var builder strings.Builder
	builder.Grow(length)
	max := big.NewInt(int64(len(alphabet)))

	for i := 0; i < length; i++ {
		n, err := rand.Int(rand.Reader, max)
		if err != nil {
			return "", err
		}
		builder.WriteByte(alphabet[n.Int64()])
	}

	return builder.String(), nil
}

func randomInt(max int64) (int64, error) {
	n, err := rand.Int(rand.Reader, big.NewInt(max))
	if err != nil {
		return 0, err
	}
	return n.Int64(), nil
}

func randomRange(min int64, max int64) (int64, error) {
	if max <= min {
		return min, nil
	}
	n, err := randomInt(max - min + 1)
	if err != nil {
		return 0, err
	}
	return min + n, nil
}

func renderCaptchaSVG(code string) (string, error) {
	var builder strings.Builder
	builder.WriteString(`<svg xmlns="http://www.w3.org/2000/svg" width="160" height="52" viewBox="0 0 160 52" role="img">`)
	builder.WriteString(`<rect width="160" height="52" rx="8" fill="#F8FAFC"/>`)

	colors := []string{"#3A7CA5", "#4F8A6B", "#D4AF37", "#0B132B", "#9F5F80"}
	for i := 0; i < 8; i++ {
		x1, err := randomRange(0, 160)
		if err != nil {
			return "", err
		}
		y1, err := randomRange(0, 52)
		if err != nil {
			return "", err
		}
		x2, err := randomRange(0, 160)
		if err != nil {
			return "", err
		}
		y2, err := randomRange(0, 52)
		if err != nil {
			return "", err
		}
		color := colors[i%len(colors)]
		fmt.Fprintf(&builder, `<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-width="1.2" opacity="0.24"/>`, x1, y1, x2, y2, color)
	}

	for i, char := range code {
		x := int64(18 + i*25)
		dx, err := randomRange(-3, 3)
		if err != nil {
			return "", err
		}
		y, err := randomRange(32, 40)
		if err != nil {
			return "", err
		}
		rotate, err := randomRange(-18, 18)
		if err != nil {
			return "", err
		}
		color := colors[(i+1)%len(colors)]
		text := html.EscapeString(string(char))
		fmt.Fprintf(&builder, `<text x="%d" y="%d" transform="rotate(%d %d %d)" fill="%s" font-family="Verdana,Arial,sans-serif" font-size="26" font-weight="700">%s</text>`, x+dx, y, rotate, x+dx, y, color, text)
	}

	for i := 0; i < 18; i++ {
		cx, err := randomRange(0, 160)
		if err != nil {
			return "", err
		}
		cy, err := randomRange(0, 52)
		if err != nil {
			return "", err
		}
		color := colors[(i+2)%len(colors)]
		fmt.Fprintf(&builder, `<circle cx="%d" cy="%d" r="1.2" fill="%s" opacity="0.28"/>`, cx, cy, color)
	}

	builder.WriteString(`</svg>`)
	return builder.String(), nil
}

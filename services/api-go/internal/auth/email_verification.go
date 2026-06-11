package auth

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"crypto/tls"
	"encoding/hex"
	"errors"
	"fmt"
	"log"
	"mime"
	"net"
	"net/mail"
	"net/smtp"
	"strconv"
	"strings"
	"sync"
	"time"
)

type EmailVerificationConfig struct {
	TTL         time.Duration
	Cooldown    time.Duration
	MaxAttempts int
	DebugCode   bool
}

type EmailVerificationResult struct {
	ExpiresInSeconds  int    `json:"expires_in_seconds"`
	RetryAfterSeconds int    `json:"retry_after_seconds"`
	DebugCode         string `json:"debug_code,omitempty"`
}

type EmailCodeCooldownError struct {
	RetryAfter time.Duration
}

func (e EmailCodeCooldownError) Error() string {
	return "email verification code cooldown"
}

type EmailSender interface {
	SendVerificationCode(ctx context.Context, email string, code string) error
}

type EmailVerificationService struct {
	store  *MemoryEmailVerificationStore
	sender EmailSender
	config EmailVerificationConfig
}

func NewEmailVerificationService(store *MemoryEmailVerificationStore, sender EmailSender, config EmailVerificationConfig) *EmailVerificationService {
	if store == nil {
		store = NewMemoryEmailVerificationStore()
	}
	if sender == nil {
		sender = LogEmailSender{Logger: log.Default()}
	}
	if config.TTL <= 0 {
		config.TTL = 10 * time.Minute
	}
	if config.Cooldown <= 0 {
		config.Cooldown = 60 * time.Second
	}
	if config.MaxAttempts <= 0 {
		config.MaxAttempts = 5
	}

	return &EmailVerificationService{store: store, sender: sender, config: config}
}

func (s *EmailVerificationService) RequestCode(ctx context.Context, email string) (EmailVerificationResult, error) {
	email = normalizeEmail(email)
	now := time.Now().UTC()

	if retryAfter := s.store.RetryAfter(email, now); retryAfter > 0 {
		return EmailVerificationResult{}, EmailCodeCooldownError{RetryAfter: retryAfter}
	}

	code, err := randomNumericCode(6)
	if err != nil {
		return EmailVerificationResult{}, err
	}

	if err := s.sender.SendVerificationCode(ctx, email, code); err != nil {
		return EmailVerificationResult{}, fmt.Errorf("%w: %v", ErrEmailCodeSendFailed, err)
	}

	s.store.Save(email, hashEmailCode(email, code), now, s.config.TTL, s.config.Cooldown, s.config.MaxAttempts)

	result := EmailVerificationResult{
		ExpiresInSeconds:  secondsCeil(s.config.TTL),
		RetryAfterSeconds: secondsCeil(s.config.Cooldown),
	}
	if s.config.DebugCode {
		result.DebugCode = code
	}
	return result, nil
}

func (s *EmailVerificationService) Verify(email string, code string) error {
	email = normalizeEmail(email)
	code = strings.TrimSpace(code)
	if email == "" || code == "" {
		return ErrInvalidEmailCode
	}
	return s.store.Verify(email, hashEmailCode(email, code), time.Now().UTC())
}

type emailVerificationRecord struct {
	CodeHash     string
	ExpiresAt    time.Time
	NextSendAt   time.Time
	AttemptsLeft int
}

type MemoryEmailVerificationStore struct {
	mu      sync.Mutex
	records map[string]emailVerificationRecord
}

func NewMemoryEmailVerificationStore() *MemoryEmailVerificationStore {
	return &MemoryEmailVerificationStore{records: map[string]emailVerificationRecord{}}
}

func (s *MemoryEmailVerificationStore) RetryAfter(email string, now time.Time) time.Duration {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.records[email]
	if !ok {
		return 0
	}
	if now.After(record.ExpiresAt) {
		delete(s.records, email)
		return 0
	}
	if now.Before(record.NextSendAt) {
		return record.NextSendAt.Sub(now)
	}
	return 0
}

func (s *MemoryEmailVerificationStore) Save(email string, codeHash string, now time.Time, ttl time.Duration, cooldown time.Duration, maxAttempts int) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.cleanupLocked(now)
	s.records[email] = emailVerificationRecord{
		CodeHash:     codeHash,
		ExpiresAt:    now.Add(ttl),
		NextSendAt:   now.Add(cooldown),
		AttemptsLeft: maxAttempts,
	}
}

func (s *MemoryEmailVerificationStore) Verify(email string, codeHash string, now time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	record, ok := s.records[email]
	if !ok {
		return ErrInvalidEmailCode
	}
	if now.After(record.ExpiresAt) || record.AttemptsLeft <= 0 {
		delete(s.records, email)
		return ErrInvalidEmailCode
	}

	if subtle.ConstantTimeCompare([]byte(record.CodeHash), []byte(codeHash)) != 1 {
		record.AttemptsLeft--
		if record.AttemptsLeft <= 0 {
			delete(s.records, email)
			return ErrInvalidEmailCode
		}
		s.records[email] = record
		return ErrInvalidEmailCode
	}

	delete(s.records, email)
	return nil
}

func (s *MemoryEmailVerificationStore) cleanupLocked(now time.Time) {
	for email, record := range s.records {
		if now.After(record.ExpiresAt) {
			delete(s.records, email)
		}
	}
}

func randomNumericCode(length int) (string, error) {
	return randomCode(length, "0123456789")
}

func hashEmailCode(email string, code string) string {
	sum := sha256.Sum256([]byte(normalizeEmail(email) + ":" + strings.TrimSpace(code)))
	return hex.EncodeToString(sum[:])
}

func secondsCeil(duration time.Duration) int {
	if duration <= 0 {
		return 0
	}
	return int((duration + time.Second - time.Nanosecond) / time.Second)
}

type LogEmailSender struct {
	Logger *log.Logger
}

func (s LogEmailSender) SendVerificationCode(ctx context.Context, email string, code string) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	default:
	}

	logger := s.Logger
	if logger == nil {
		logger = log.Default()
	}
	logger.Printf("registration email verification code: email=%s code=%s", email, code)
	return nil
}

type SMTPEmailSenderConfig struct {
	Host     string
	Port     int
	Username string
	Password string
	From     string
	UseTLS   bool
}

func NewEmailSender(config SMTPEmailSenderConfig) EmailSender {
	if strings.TrimSpace(config.Host) == "" {
		return LogEmailSender{Logger: log.Default()}
	}
	if config.Port <= 0 {
		config.Port = 587
	}
	if strings.TrimSpace(config.From) == "" {
		config.From = "IELTS Speaking <no-reply@localhost>"
	}
	return SMTPEmailSender{config: config}
}

type SMTPEmailSender struct {
	config SMTPEmailSenderConfig
}

func (s SMTPEmailSender) SendVerificationCode(ctx context.Context, email string, code string) error {
	done := make(chan error, 1)
	go func() {
		done <- s.send(email, code)
	}()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case err := <-done:
		return err
	}
}

func (s SMTPEmailSender) send(email string, code string) error {
	address := net.JoinHostPort(s.config.Host, strconv.Itoa(s.config.Port))
	from := envelopeAddress(s.config.From)
	message := buildVerificationEmail(s.config.From, email, code)

	var auth smtp.Auth
	if strings.TrimSpace(s.config.Username) != "" {
		auth = smtp.PlainAuth("", s.config.Username, s.config.Password, s.config.Host)
	}

	if s.config.UseTLS {
		return s.sendImplicitTLS(address, from, email, message, auth)
	}
	return smtp.SendMail(address, auth, from, []string{email}, message)
}

func (s SMTPEmailSender) sendImplicitTLS(address string, from string, to string, message []byte, auth smtp.Auth) error {
	conn, err := tls.Dial("tcp", address, &tls.Config{ServerName: s.config.Host, MinVersion: tls.VersionTLS12})
	if err != nil {
		return err
	}
	client, err := smtp.NewClient(conn, s.config.Host)
	if err != nil {
		conn.Close()
		return err
	}
	defer client.Close()

	if auth != nil {
		if err := client.Auth(auth); err != nil {
			return err
		}
	}
	if err := client.Mail(from); err != nil {
		return err
	}
	if err := client.Rcpt(to); err != nil {
		return err
	}
	writer, err := client.Data()
	if err != nil {
		return err
	}
	if _, err := writer.Write(message); err != nil {
		writer.Close()
		return err
	}
	if err := writer.Close(); err != nil {
		return err
	}
	return client.Quit()
}

func envelopeAddress(value string) string {
	parsed, err := mail.ParseAddress(value)
	if err == nil {
		return parsed.Address
	}
	return strings.TrimSpace(value)
}

func buildVerificationEmail(from string, to string, code string) []byte {
	subject := mime.QEncoding.Encode("UTF-8", "IELTS Speaking 注册验证码")
	body := fmt.Sprintf("你的 IELTS Speaking 注册验证码是：%s\r\n\r\n验证码会在短时间内失效。如非本人操作，可以忽略这封邮件。\r\n", code)

	var builder strings.Builder
	builder.WriteString("From: " + from + "\r\n")
	builder.WriteString("To: " + (&mail.Address{Address: to}).String() + "\r\n")
	builder.WriteString("Subject: " + subject + "\r\n")
	builder.WriteString("Date: " + time.Now().Format(time.RFC1123Z) + "\r\n")
	builder.WriteString("MIME-Version: 1.0\r\n")
	builder.WriteString("Content-Type: text/plain; charset=UTF-8\r\n")
	builder.WriteString("Content-Transfer-Encoding: 8bit\r\n")
	builder.WriteString("\r\n")
	builder.WriteString(body)
	return []byte(builder.String())
}

func IsEmailCodeCooldown(err error) (EmailCodeCooldownError, bool) {
	var cooldown EmailCodeCooldownError
	if errors.As(err, &cooldown) {
		return cooldown, true
	}
	return EmailCodeCooldownError{}, false
}

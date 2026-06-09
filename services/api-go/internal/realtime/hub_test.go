package realtime

import (
	"encoding/json"
	"testing"
	"time"
)

func TestHubBroadcastTargetsSession(t *testing.T) {
	hub := NewHub()
	clientA := hub.NewClient("session_001", "user_001")
	clientB := hub.NewClient("session_001", "user_001")
	clientOther := hub.NewClient("session_002", "user_001")
	hub.Register(clientA)
	hub.Register(clientB)
	hub.Register(clientOther)
	defer hub.Unregister(clientA)
	defer hub.Unregister(clientB)
	defer hub.Unregister(clientOther)

	count, err := hub.Broadcast("session_001", SessionEvent{
		Type:      EventTimerTick,
		SessionID: "session_001",
		RunID:     "run_001",
		Payload:   json.RawMessage(`{"remaining_seconds":30}`),
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		t.Fatalf("Broadcast() error = %v", err)
	}
	if count != 2 {
		t.Fatalf("Broadcast() count = %d, want 2", count)
	}

	assertMessage(t, clientA.send)
	assertMessage(t, clientB.send)
	assertNoMessage(t, clientOther.send)
}

func TestSessionEventValidateRejectsWrongSession(t *testing.T) {
	err := (SessionEvent{
		Type:      EventTimerTick,
		SessionID: "session_002",
		RunID:     "run_001",
		Payload:   json.RawMessage(`{}`),
		CreatedAt: time.Now().UTC().Format(time.RFC3339Nano),
	}).Validate("session_001")
	if err == nil {
		t.Fatal("Validate() expected error for wrong session")
	}
}

func assertMessage(t *testing.T, ch <-chan []byte) {
	t.Helper()
	select {
	case message := <-ch:
		if len(message) == 0 {
			t.Fatal("empty broadcast message")
		}
	case <-time.After(time.Second):
		t.Fatal("expected broadcast message")
	}
}

func assertNoMessage(t *testing.T, ch <-chan []byte) {
	t.Helper()
	select {
	case message := <-ch:
		t.Fatalf("unexpected message: %s", string(message))
	case <-time.After(50 * time.Millisecond):
	}
}

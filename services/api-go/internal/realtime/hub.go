package realtime

import (
	"encoding/json"
	"sync"
)

const defaultClientBuffer = 32

type Hub struct {
	mu      sync.RWMutex
	clients map[string]map[*Client]struct{}
	buffer  int
}

func NewHub() *Hub {
	return &Hub{
		clients: map[string]map[*Client]struct{}{},
		buffer:  defaultClientBuffer,
	}
}

func (h *Hub) NewClient(sessionID string, userID string) *Client {
	buffer := h.buffer
	if buffer <= 0 {
		buffer = defaultClientBuffer
	}
	return &Client{
		hub:       h,
		sessionID: sessionID,
		userID:    userID,
		send:      make(chan []byte, buffer),
	}
}

func (h *Hub) Register(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	if h.clients[client.sessionID] == nil {
		h.clients[client.sessionID] = map[*Client]struct{}{}
	}
	h.clients[client.sessionID][client] = struct{}{}
}

func (h *Hub) Unregister(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()

	sessionClients := h.clients[client.sessionID]
	if sessionClients == nil {
		return
	}
	if _, ok := sessionClients[client]; !ok {
		return
	}
	delete(sessionClients, client)
	close(client.send)
	if len(sessionClients) == 0 {
		delete(h.clients, client.sessionID)
	}
}

func (h *Hub) Broadcast(sessionID string, event SessionEvent) (int, error) {
	if err := event.Validate(sessionID); err != nil {
		return 0, err
	}
	message, err := json.Marshal(event)
	if err != nil {
		return 0, err
	}
	return h.BroadcastRaw(sessionID, message), nil
}

func (h *Hub) BroadcastRaw(sessionID string, message []byte) int {
	h.mu.RLock()
	defer h.mu.RUnlock()

	count := 0
	for client := range h.clients[sessionID] {
		select {
		case client.send <- message:
			count++
		default:
			go h.Unregister(client)
		}
	}
	return count
}

func (h *Hub) ClientCount(sessionID string) int {
	h.mu.RLock()
	defer h.mu.RUnlock()

	return len(h.clients[sessionID])
}

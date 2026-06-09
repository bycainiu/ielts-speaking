FROM golang:1.23-alpine AS builder

WORKDIR /src

COPY services/api-go/go.mod services/api-go/go.sum ./
RUN go mod download

COPY services/api-go ./
RUN CGO_ENABLED=0 GOOS=linux go build -o /api ./cmd/api

FROM alpine:3.21 AS runtime

RUN adduser -D -H apiuser
USER apiuser

COPY --from=builder /api /api

EXPOSE 8080

ENTRYPOINT ["/api"]


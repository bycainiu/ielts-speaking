package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/ielts-speaking/platform/services/api-go/internal/config"
	"github.com/ielts-speaking/platform/services/api-go/internal/db"
	"github.com/ielts-speaking/platform/services/api-go/internal/server"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	if len(os.Args) > 1 {
		switch os.Args[1] {
		case "healthcheck":
			runHealthcheck(cfg)
			return
		case "migrate":
			command := "up"
			if len(os.Args) > 2 {
				command = os.Args[2]
			}
			if err := db.RunMigrations(cfg.DatabaseURL, command); err != nil {
				log.Fatalf("run migrations: %v", err)
			}
			return
		}
	}

	database, err := db.Open(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer database.Close()

	router := server.NewRouterWithDB(cfg, database)
	addr := fmt.Sprintf(":%s", cfg.HTTPPort)

	srv := &http.Server{
		Addr:              addr,
		Handler:           router,
		ReadHeaderTimeout: 5 * time.Second,
	}

	log.Printf("api-go listening on %s", addr)
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("listen: %v", err)
	}
}

func runHealthcheck(cfg config.Config) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://127.0.0.1:"+cfg.HTTPPort+"/healthz", nil)
	if err != nil {
		log.Fatalf("create healthcheck request: %v", err)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		log.Fatalf("healthcheck failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		log.Fatalf("healthcheck returned %s", resp.Status)
	}
}

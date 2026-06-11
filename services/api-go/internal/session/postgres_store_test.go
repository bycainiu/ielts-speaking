package session

import "testing"

func TestBuildAdminSessionContextLookupPreservesNonUUIDSessionIDs(t *testing.T) {
	args, placeholders := buildAdminSessionContextLookup([]string{
		"web_obs_1781002648909",
		"550e8400-e29b-41d4-a716-446655440000",
		"web_obs_1781002648909",
		" ",
	})

	if len(args) != 2 {
		t.Fatalf("args len = %d, want 2", len(args))
	}
	if first, ok := args[0].(string); !ok || first != "web_obs_1781002648909" {
		t.Fatalf("args[0] = %#v, want web_obs_1781002648909", args[0])
	}
	if second, ok := args[1].(string); !ok || second != "550e8400-e29b-41d4-a716-446655440000" {
		t.Fatalf("args[1] = %#v, want valid uuid string", args[1])
	}
	if placeholders != "$1, $2" {
		t.Fatalf("placeholders = %q, want %q", placeholders, "$1, $2")
	}
}

func TestLookupOrderFromStringsKeepsFirstOccurrence(t *testing.T) {
	order := lookupOrderFromStrings([]string{
		"sha256:first",
		"sha256:second",
		"sha256:first",
	})

	if len(order) != 2 {
		t.Fatalf("order len = %d, want 2", len(order))
	}
	if order["sha256:first"] != 0 {
		t.Fatalf("first order = %d, want 0", order["sha256:first"])
	}
	if order["sha256:second"] != 1 {
		t.Fatalf("second order = %d, want 1", order["sha256:second"])
	}
}

func TestSortAdminUserContextsByLookupUsesInputOrder(t *testing.T) {
	items := []AdminUserContext{
		{UserID: "user_2", UserHash: "sha256:second"},
		{UserID: "user_1", UserHash: "sha256:first"},
	}

	sorted := sortAdminUserContextsByLookup(items, map[string]int{
		"sha256:first":  0,
		"sha256:second": 1,
	})

	if sorted[0].UserHash != "sha256:first" {
		t.Fatalf("sorted[0] = %q, want sha256:first", sorted[0].UserHash)
	}
	if sorted[1].UserHash != "sha256:second" {
		t.Fatalf("sorted[1] = %q, want sha256:second", sorted[1].UserHash)
	}
}

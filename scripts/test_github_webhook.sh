#!/bin/bash
# Test GitHub webhook locally
# Usage: ./scripts/test_github_webhook.sh [event_type]
# Examples:
#   ./scripts/test_github_webhook.sh push
#   ./scripts/test_github_webhook.sh pull_request
#   ./scripts/test_github_webhook.sh issue_comment

set -e

WEBHOOK_URL="${WEBHOOK_URL:-http://localhost:8000/webhooks/github}"
EVENT_TYPE="${1:-push}"

echo "Testing GitHub webhook: $EVENT_TYPE"
echo "URL: $WEBHOOK_URL"
echo ""

case "$EVENT_TYPE" in
    push)
        PAYLOAD='{"ref":"refs/heads/main","repository":{"full_name":"htelsiz/glyx"},"pusher":{"name":"htelsiz"},"commits":[{"message":"Test commit from webhook test"}],"installation":{"id":12345}}'
        ;;
    pull_request)
        PAYLOAD='{"action":"opened","pull_request":{"number":42,"title":"Test PR from webhook","user":{"login":"htelsiz"},"html_url":"https://github.com/htelsiz/glyx/pull/42","merged":false},"repository":{"full_name":"htelsiz/glyx"},"installation":{"id":12345}}'
        ;;
    issue_comment)
        PAYLOAD='{"action":"created","issue":{"number":123,"title":"Test Issue"},"comment":{"user":{"login":"htelsiz"},"body":"@julian please review this test","html_url":"https://github.com/htelsiz/glyx/issues/123#comment"},"repository":{"full_name":"htelsiz/glyx"},"installation":{"id":12345}}'
        ;;
    issues)
        PAYLOAD='{"action":"opened","issue":{"number":456,"title":"Test Issue from webhook","user":{"login":"htelsiz"},"html_url":"https://github.com/htelsiz/glyx/issues/456"},"repository":{"full_name":"htelsiz/glyx"},"installation":{"id":12345}}'
        ;;
    *)
        echo "Unknown event type: $EVENT_TYPE"
        echo "Available: push, pull_request, issue_comment, issues"
        exit 1
        ;;
esac

echo "Payload:"
echo "$PAYLOAD" | python3 -m json.tool
echo ""

curl -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -H "X-GitHub-Event: $EVENT_TYPE" \
    -H "X-GitHub-Delivery: test-$(date +%s)" \
    -d "$PAYLOAD" \
    -w "\n\nHTTP Status: %{http_code}\n"

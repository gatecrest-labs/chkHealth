#!/usr/bin/env bash
# Generates a self-signed TLS cert for local HTTPS dev.
# Valid for 397 days (browser max). Includes SANs for localhost,
# 127.0.0.1, and the current machine's LAN IP so the browser doesn't
# flag an IP mismatch.

set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")/.." && pwd)/certs"
mkdir -p "$CERT_DIR"

# Detect the primary LAN IP (en0 = Wi-Fi on Mac, fallback to en1)
LAN_IP=$(ipconfig getifaddr en0 2>/dev/null \
      || ipconfig getifaddr en1 2>/dev/null \
      || echo "")

SAN="DNS:localhost,IP:127.0.0.1"
if [[ -n "$LAN_IP" ]]; then
    SAN="$SAN,IP:$LAN_IP"
    echo "Including LAN IP in SAN: $LAN_IP"
fi

openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/key.pem" \
    -out   "$CERT_DIR/cert.pem" \
    -days  397 \
    -subj  "/CN=chkHealth-dev" \
    -addext "subjectAltName=$SAN"

chmod 600 "$CERT_DIR/key.pem"
chmod 644 "$CERT_DIR/cert.pem"

echo ""
echo "Cert written to $CERT_DIR"
echo ""
echo "Run the app over HTTPS with:"
echo "  uv run flask run --host=0.0.0.0 --port=5000 --cert=certs/cert.pem --key=certs/key.pem"
if [[ -n "$LAN_IP" ]]; then
    echo ""
    echo "Network access:  https://$LAN_IP:5000"
fi
echo ""
echo "To avoid browser warnings, add cert.pem to your Mac's Keychain:"
echo "  sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain certs/cert.pem"

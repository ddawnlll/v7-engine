"""Colab Auth — manual PKCE OAuth flow for Windows.
Usage: python colab/colab_auth.py
"""
import secrets, hashlib, base64, json, os, webbrowser
import urllib.parse, urllib.request

CLIENT_ID = "764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com"
CLIENT_SECRET = "d-FL95Q19q7MQmFpd7hHD0Ty"
TOKEN_PATH = os.path.expanduser("~/.config/colab-cli/token.json")
REDIRECT_URI = "http://localhost"

def _b64(s):
    return base64.urlsafe_b64encode(s).rstrip(b"=").decode()

# 1. PKCE
verifier = _b64(secrets.token_bytes(32))
challenge = _b64(hashlib.sha256(verifier.encode()).digest())

# 2. Auth URL
params = {
    "response_type": "code",
    "client_id": CLIENT_ID,
    "redirect_uri": REDIRECT_URI,
    "scope": "openid https://www.googleapis.com/auth/userinfo.profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/cloud-platform https://www.googleapis.com/auth/colaboratory https://www.googleapis.com/auth/drive.file",
    "state": _b64(secrets.token_bytes(16)),
    "code_challenge": challenge,
    "code_challenge_method": "S256",
    "prompt": "consent",
    "token_usage": "remote",
    "access_type": "offline",
}
url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

print("=" * 60)
print("  COLAB AUTH — PKCE Flow")
print("=" * 60)
print()
print("1. Bu URL'yi browser'da aç:")
print()
print(f"  {url}")
print()
print("2. Google hesabina gir ve izin ver")
print("3. Browser'daki authorization code'u kopyala")
print("4. Asagiya yapistir + Enter")
print()

code = input("Authorization code: ").strip()

# 3. Exchange code for tokens
print("\nExchanging code for tokens...")
data = urllib.parse.urlencode({
    "code": code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
    "code_verifier": verifier,
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)

resp = urllib.request.urlopen(req)
tokens = json.loads(resp.read())

# 4. Save token
creds = {
    "token": tokens["access_token"],
    "refresh_token": tokens.get("refresh_token"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": tokens["scope"].split(),
}
os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
with open(TOKEN_PATH, "w") as f:
    json.dump(creds, f, indent=2)

print(f"\n✅ Auth basarili! Token kaydedildi: {TOKEN_PATH}")
print(f"   Access token: {tokens['access_token'][:20]}...")
print(f"   Refresh token: {tokens.get('refresh_token', 'NONE')[:20]}...")
print(f"\nArtik su komutu calistirabilirsin:")
print(f"   python colab/colab.py new --gpu T4 -s v7-training")

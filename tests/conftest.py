import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(scope="session")
def local_tsa(tmp_path_factory):
    """A throwaway RFC 3161 timestamp authority built with openssl, so tests make real tokens offline."""
    d = tmp_path_factory.mktemp("tsa")
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "tsa.key"),
                    "-out", str(d / "tsa.crt"), "-days", "2", "-subj", "/CN=IndieWard Test TSA",
                    "-addext", "extendedKeyUsage=critical,timeStamping"], check=True, capture_output=True)
    (d / "serial").write_text("01\n")
    cfg = d / "tsa.cnf"
    cfg.write_text(f"""[ tsa ]
default_tsa = tsa_config1
[ tsa_config1 ]
dir = {d}
serial = $dir/serial
crypto_device = builtin
signer_cert = $dir/tsa.crt
signer_key = $dir/tsa.key
signer_digest = sha256
default_policy = 1.2.3.4.1
digests = sha256
accuracy = secs:1
ordering = yes
tsa_name = no
ess_cert_id_chain = no
ess_cert_id_alg = sha256
""")

    def post(url, data, content_type, timeout=30.0):
        if content_type == "application/timestamp-query":
            q = d / "q.tsq"
            q.write_bytes(data)
            subprocess.run(["openssl", "ts", "-reply", "-config", str(cfg), "-queryfile", str(q), "-out",
                            str(d / "r.tsr")], check=True, capture_output=True)
            return (d / "r.tsr").read_bytes()
        # OpenTimestamps calendar stub: a pending attestation-shaped blob (not a real Bitcoin proof)
        return b"\xf0\x10" + b"\x00" * 16 + b"\x08\x00\x83\xdf\xe3\x0d\x2e\xf9\x0c\x8e" + b"\x1btest-calendar"

    return {"dir": d, "post": post, "cert": d / "tsa.crt"}

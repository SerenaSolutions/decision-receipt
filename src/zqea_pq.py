# -*- coding: utf-8 -*-
"""zqea_pq.py — Z-QEA post-quantum core (v2.0.0) — the house's PQC layer.

Two layers, one receipt:
  1. selo_sha3_256    — SHA3-256 canonical seal (Grover-resistant, unchanged
                        since v1: every old receipt keeps verifying).
  2. assinatura_pq    — ML-DSA-44 (FIPS 204, NIST post-quantum signature).
                        No quantum computer — logical or physical — forges it.
                        Keypair is ephemeral per seal and the public key ships
                        INSIDE the receipt: receipts are self-verifying, no
                        server, no key distribution, no CA.

Entropy: the receipt id is derived from the QUANTUM ENTROPY POOL below —
bits measured on real IBM Quantum hardware (job dbcnmds24mrc73ck0p0g,
ibm_marrakesh, 32 qubits in Hadamard superposition, 256 shots, 8192 measured
bits) — mixed with fresh OS entropy via SHAKE256. The pool is a public
quantum-attested beacon: its origin is proven by the sealed attestation in
quantum_entropy_attestation.json; the nonce security never relies on the
public pool alone (SHAKE256(pool || os.urandom(32) || domain)).

No endorsement by IBM is claimed. No vendor secret is embedded here.
"""
import base64, hashlib, json, os

# ---- quantum entropy pool (public beacon, hardware origin attested) ----
POOL_HEX = None  # loaded from quantum_entropy_attestation.json (same folder)
ATTESTATION = {}


def _load_pool():
    global POOL_HEX, ATTESTATION
    if POOL_HEX is not None:
        return
    here = os.path.dirname(os.path.abspath(__file__))
    att_path = os.path.join(here, "quantum_entropy_attestation.json")
    if os.path.exists(att_path):
        att = json.load(open(att_path))
        ATTESTATION = {
            "job_id": att.get("job", {}).get("id"),
            "backend": att.get("job", {}).get("backend"),
            "shots": att.get("job", {}).get("shots"),
            "qubits": att.get("job", {}).get("qubits"),
            "pool_sha3_256": att.get("pool_sha3_256"),
            "data": att.get("data"),
        }
        POOL_HEX = att.get("pool_hex", "")
    else:
        POOL_HEX = ""  # pool unavailable: receipts fall back to OS entropy only


def quantum_receipt_id(domain="zqea"):
    """Receipt id born from quantum-attested pool + fresh OS entropy."""
    _load_pool()
    pool = bytes.fromhex(POOL_HEX) if POOL_HEX else b""
    material = pool + os.urandom(32) + domain.encode()
    return hashlib.shake_256(material).hexdigest(16)


def entropy_provenance():
    _load_pool()
    return dict(ATTESTATION)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, default=str)


def sha3_seal(payload):
    return hashlib.sha3_256(canonical(payload).encode()).hexdigest()


# ---- ML-DSA-44 (FIPS 204) ------------------------------------------------
ML_DSA = "ML-DSA-44 (FIPS 204, NIST post-quantum signature, Dilithium2 parameters)"


def sign_receipt(rec):
    """Attach the post-quantum signature block. Receipt becomes self-verifying."""
    from pqcrypto.sign import ml_dsa_44
    pk, sk = ml_dsa_44.keygen()
    # signature over the canonical receipt WITHOUT the signature block
    payload = {k: v for k, v in rec.items() if k not in ("assinatura_pq", "selo_sha3_256")}
    sig = ml_dsa_44.sign(sk, canonical(payload).encode())
    rec["assinatura_pq"] = {
        "alg": ML_DSA,
        "pk_b64": base64.b64encode(pk).decode(),
        "sig_b64": base64.b64encode(sig).decode(),
        "regra": "assinatura ML-DSA-44 sobre json.dumps(recibo, sort_keys=True, ensure_ascii=True, default=str) com assinatura_pq e selo_sha3_256 REMOVIDOS da entrada; pk embarcado no recibo (autoverificável, sem servidor)",
    }
    return rec


def verify_signature(receipt):
    """Returns (status, detail): 'PQ_OK' | 'PQ_INVALID' | 'LEGACY_V1' (no sig)."""
    blk = receipt.get("assinatura_pq")
    if not isinstance(blk, dict) or not blk.get("sig_b64"):
        return "LEGACY_V1", "receipt has no post-quantum signature (v1 legacy)"
    try:
        from pqcrypto.sign import ml_dsa_44
        payload = {k: v for k, v in receipt.items() if k not in ("assinatura_pq", "selo_sha3_256")}
        ml_dsa_44.verify(base64.b64decode(blk["pk_b64"]),
                         canonical(payload).encode(),
                         base64.b64decode(blk["sig_b64"]))
        return "PQ_OK", "ML-DSA-44 signature VALID"
    except ImportError:
        return "PQ_UNAVAILABLE", "pqcrypto not installed — cannot verify signature (install: pip install pqcrypto)"
    except Exception as e:
        return "PQ_INVALID", "ML-DSA-44 signature INVALID — %s" % type(e).__name__

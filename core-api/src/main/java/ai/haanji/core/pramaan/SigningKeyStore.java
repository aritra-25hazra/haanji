package ai.haanji.core.pramaan;

import org.bouncycastle.crypto.params.Ed25519PrivateKeyParameters;
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters;
import org.bouncycastle.crypto.signers.Ed25519Signer;
import org.springframework.stereotype.Component;

import java.security.SecureRandom;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Holds one Ed25519 signing key per tenant.
 *
 * <p>The implementation here keeps material in memory so the service runs on a
 * laptop with nothing else installed. In a deployment the private half never
 * leaves the KMS: {@code key_ref} in {@code tenant_keys} is a handle, the
 * public half is stored in the clear so anyone can verify, and {@link #sign}
 * becomes a call to the KMS. Nothing else in the system changes, because
 * nothing else in the system ever sees a private key.
 */
@Component
public class SigningKeyStore {

    public record Key(String keyId, Ed25519PrivateKeyParameters priv,
                      Ed25519PublicKeyParameters pub) { }

    private final Map<UUID, Key> keys = new ConcurrentHashMap<>();
    private final SecureRandom random = new SecureRandom();

    public Key activeKeyFor(UUID tenantId) {
        return keys.computeIfAbsent(tenantId, t -> {
            Ed25519PrivateKeyParameters priv = new Ed25519PrivateKeyParameters(random);
            return new Key("k_" + UUID.randomUUID().toString().replace("-", "").substring(0, 12),
                    priv, priv.generatePublicKey());
        });
    }

    public byte[] sign(Key key, byte[] message) {
        Ed25519Signer signer = new Ed25519Signer();
        signer.init(true, key.priv());
        signer.update(message, 0, message.length);
        return signer.generateSignature();
    }

    public boolean verify(Ed25519PublicKeyParameters pub, byte[] message, byte[] signature) {
        Ed25519Signer verifier = new Ed25519Signer();
        verifier.init(false, pub);
        verifier.update(message, 0, message.length);
        return verifier.verifySignature(signature);
    }

    public String publicKeyHex(UUID tenantId) {
        return HexFormat.of().formatHex(activeKeyFor(tenantId).pub().getEncoded());
    }
}

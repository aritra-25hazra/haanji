package ai.haanji.core.domain;

import jakarta.persistence.*;
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

/**
 * One sealed entry in the Pramaan chain.
 *
 * <p>There is no setter on this class and no update path in any repository:
 * a receipt is written once and read forever. The database enforces the same
 * rule with a trigger, because an ORM guarantee is only a guarantee for code
 * that goes through the ORM.
 */
@Entity
@Table(name = "receipts")
@org.hibernate.annotations.Immutable
public class Receipt {

    @Id @GeneratedValue
    @Column(name = "receipt_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false, updatable = false)
    private UUID tenantId;

    @Column(nullable = false, updatable = false)
    private long seq;

    @Column(name = "conversation_id", updatable = false)
    private UUID conversationId;

    @Column(nullable = false, updatable = false)
    private String action;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(name = "action_args", nullable = false, updatable = false)
    private Map<String, Object> actionArgs;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(nullable = false, updatable = false)
    private Map<String, Object> confirmation;

    @Column(name = "transcript_excerpt", nullable = false, updatable = false)
    private String transcriptExcerpt;

    @Column(name = "agent_config_version", nullable = false, updatable = false)
    private int agentConfigVersion;

    @Column(name = "occurred_at", nullable = false, updatable = false)
    private Instant occurredAt;

    @Column(name = "prev_hash", nullable = false, updatable = false)
    private byte[] prevHash;

    @Column(name = "payload_hash", nullable = false, updatable = false)
    private byte[] payloadHash;

    @Column(name = "chain_hash", nullable = false, updatable = false)
    private byte[] chainHash;

    @Column(nullable = false, updatable = false)
    private byte[] signature;

    @Column(name = "key_id", nullable = false, updatable = false)
    private String keyId;

    @Column(name = "short_code", nullable = false, updatable = false)
    private String shortCode;

    protected Receipt() { }

    public Receipt(UUID tenantId, long seq, UUID conversationId, String action,
                   Map<String, Object> actionArgs, Map<String, Object> confirmation,
                   String transcriptExcerpt, int agentConfigVersion, Instant occurredAt,
                   byte[] prevHash, byte[] payloadHash, byte[] chainHash,
                   byte[] signature, String keyId, String shortCode) {
        this.tenantId = tenantId;
        this.seq = seq;
        this.conversationId = conversationId;
        this.action = action;
        this.actionArgs = actionArgs;
        this.confirmation = confirmation;
        this.transcriptExcerpt = transcriptExcerpt;
        this.agentConfigVersion = agentConfigVersion;
        this.occurredAt = occurredAt;
        this.prevHash = prevHash;
        this.payloadHash = payloadHash;
        this.chainHash = chainHash;
        this.signature = signature;
        this.keyId = keyId;
        this.shortCode = shortCode;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public long getSeq() { return seq; }
    public UUID getConversationId() { return conversationId; }
    public String getAction() { return action; }
    public Map<String, Object> getActionArgs() { return actionArgs; }
    public Map<String, Object> getConfirmation() { return confirmation; }
    public String getTranscriptExcerpt() { return transcriptExcerpt; }
    public int getAgentConfigVersion() { return agentConfigVersion; }
    public Instant getOccurredAt() { return occurredAt; }
    public byte[] getPrevHash() { return prevHash.clone(); }
    public byte[] getPayloadHash() { return payloadHash.clone(); }
    public byte[] getChainHash() { return chainHash.clone(); }
    public byte[] getSignature() { return signature.clone(); }
    public String getKeyId() { return keyId; }
    public String getShortCode() { return shortCode; }
}

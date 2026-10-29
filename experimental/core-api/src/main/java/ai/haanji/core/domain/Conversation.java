package ai.haanji.core.domain;

import jakarta.persistence.*;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "conversations")
public class Conversation {

    public enum Channel { PHONE, WHATSAPP, WEB }
    public enum Outcome { BOOKED, FAQ_ANSWERED, LEAD_CAPTURED, HANDED_OFF, ABANDONED }

    @Id @GeneratedValue
    @Column(name = "conversation_id")
    private UUID id;

    @Column(name = "tenant_id", nullable = false)
    private UUID tenantId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private Channel channel;

    @Column(name = "caller_phone")
    private String callerPhone;

    @Column(name = "started_at", nullable = false)
    private Instant startedAt = Instant.now();

    @Column(name = "ended_at")
    private Instant endedAt;

    @Enumerated(EnumType.STRING)
    private Outcome outcome;

    @Column(name = "duration_ms")
    private Integer durationMs;

    @Column(name = "recording_url")
    private String recordingUrl;

    protected Conversation() { }

    public Conversation(UUID tenantId, Channel channel, String callerPhone) {
        this.tenantId = tenantId;
        this.channel = channel;
        this.callerPhone = callerPhone;
    }

    public UUID getId() { return id; }
    public UUID getTenantId() { return tenantId; }
    public Channel getChannel() { return channel; }
    public String getCallerPhone() { return callerPhone; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getEndedAt() { return endedAt; }
    public Outcome getOutcome() { return outcome; }
    public Integer getDurationMs() { return durationMs; }

    public void finish(Outcome outcome) {
        this.outcome = outcome;
        this.endedAt = Instant.now();
        this.durationMs = (int) Duration.between(startedAt, endedAt).toMillis();
    }
}

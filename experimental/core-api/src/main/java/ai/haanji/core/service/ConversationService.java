package ai.haanji.core.service;

import ai.haanji.core.domain.Conversation;
import ai.haanji.core.repo.Repositories.ConversationRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

/**
 * The life cycle of a conversation.
 *
 * <p>A conversation is opened here rather than in the webhook controller so
 * that no write reaches a repository from the web layer: the controller
 * decides who is calling, this class decides what is recorded.
 */
@Service
public class ConversationService {

    private final ConversationRepository conversations;

    public ConversationService(ConversationRepository conversations) {
        this.conversations = conversations;
    }

    /** Opens a conversation for a caller who has just reached a tenant. */
    @Transactional
    public Conversation start(UUID tenantId, Conversation.Channel channel, String callerPhone) {
        return conversations.save(new Conversation(tenantId, channel, callerPhone));
    }
}

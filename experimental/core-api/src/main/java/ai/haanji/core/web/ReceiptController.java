package ai.haanji.core.web;

import ai.haanji.core.domain.Receipt;
import ai.haanji.core.pramaan.ChainVerifier;
import ai.haanji.core.pramaan.SigningKeyStore;
import ai.haanji.core.repo.Repositories.ReceiptRepository;
import ai.haanji.core.service.TenantContext;
import ai.haanji.core.web.dto.Dtos.*;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.bouncycastle.crypto.params.Ed25519PublicKeyParameters;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

/**
 * Reading and checking the ledger.
 *
 * <p>{@code /export} deliberately returns everything an outside party needs to
 * verify the chain without this service: the receipts and the public key. A
 * tenant who stops trusting Haanji can still prove what their agent agreed to.
 */
@RestController
@RequestMapping("/api/v1/receipts")
@Tag(name = "Pramaan", description = "Signed, tamper-evident receipts")
public class ReceiptController {

    private final ReceiptRepository receipts;
    private final ChainVerifier verifier;
    private final SigningKeyStore keys;

    public ReceiptController(ReceiptRepository receipts, ChainVerifier verifier,
                             SigningKeyStore keys) {
        this.receipts = receipts;
        this.verifier = verifier;
        this.keys = keys;
    }

    @GetMapping
    @Operation(summary = "The tenant's receipts in chain order")
    public List<ReceiptView> list() {
        return receipts.findByTenantIdOrderBySeqAsc(TenantContext.require())
                .stream().map(ReceiptController::view).toList();
    }

    @GetMapping("/{shortCode}")
    @Operation(summary = "One receipt by the code the caller was told")
    public ReceiptView byCode(@PathVariable String shortCode) {
        UUID tenantId = TenantContext.require();
        return receipts.findByTenantIdAndShortCode(tenantId, shortCode)
                .map(ReceiptController::view)
                .orElseThrow(() -> new IllegalArgumentException("no receipt " + shortCode));
    }

    @GetMapping("/verify")
    @Operation(summary = "Re-derive every hash and check every signature")
    public VerificationResponse verify() {
        UUID tenantId = TenantContext.require();
        List<Receipt> all = receipts.findByTenantIdOrderBySeqAsc(tenantId);
        Ed25519PublicKeyParameters pub = keys.activeKeyFor(tenantId).pub();
        ChainVerifier.Result result = verifier.verify(all, pub);
        return new VerificationResponse(result.ok(), result.checked(), result.firstBrokenSeq(),
                result.reason(), result.missingSeqs(), keys.publicKeyHex(tenantId));
    }

    @GetMapping(value = "/export", produces = MediaType.APPLICATION_JSON_VALUE)
    @Operation(summary = "Everything an independent auditor needs, and nothing else")
    public Object export() {
        UUID tenantId = TenantContext.require();
        return java.util.Map.of(
                "tenant_id", tenantId.toString(),
                "public_key", keys.publicKeyHex(tenantId),
                "algorithm", "Ed25519",
                "verifier", "https://github.com/haanji/pramaan-verify",
                "receipts", receipts.findByTenantIdOrderBySeqAsc(tenantId)
                        .stream().map(ReceiptController::view).toList());
    }

    private static ReceiptView view(Receipt r) {
        return new ReceiptView(r.getSeq(), r.getShortCode(), r.getAction(), r.getActionArgs(),
                r.getConfirmation(), r.getTranscriptExcerpt(), r.getOccurredAt(),
                HexFormat.of().formatHex(r.getChainHash()), r.getKeyId());
    }
}

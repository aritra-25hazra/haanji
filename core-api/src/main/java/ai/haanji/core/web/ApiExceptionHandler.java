package ai.haanji.core.web;

import ai.haanji.core.pramaan.LedgerService;
import ai.haanji.core.service.BookingService;
import ai.haanji.core.web.dto.Dtos.ErrorResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/**
 * One place where every failure becomes a response.
 *
 * <p>A slot collision is a 409 and not a 500: it is a normal thing that happens
 * on a busy Saturday, and the engine has a sensible reply for it ("wo slot abhi
 * chala gaya, doosra dekh lein?"). A refused unconfirmed write is a 422,
 * because the request was well formed but must not be honoured.
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    @ExceptionHandler(BookingService.SlotUnavailableException.class)
    public ResponseEntity<ErrorResponse> slotTaken(BookingService.SlotUnavailableException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ErrorResponse.of("slot_unavailable", e.getMessage()));
    }

    @ExceptionHandler(LedgerService.UnconfirmedWriteException.class)
    public ResponseEntity<ErrorResponse> unconfirmed(LedgerService.UnconfirmedWriteException e) {
        log.warn("refused an unconfirmed write: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY)
                .body(ErrorResponse.of("confirmation_required", e.getMessage()));
    }

    @ExceptionHandler({BookingService.UnknownServiceException.class,
                       BookingService.UnknownStaffException.class,
                       BookingService.UnknownAppointmentException.class,
                       IllegalArgumentException.class})
    public ResponseEntity<ErrorResponse> notFound(RuntimeException e) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(ErrorResponse.of("not_found", e.getMessage()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> invalid(MethodArgumentNotValidException e) {
        String detail = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .reduce((a, b) -> a + "; " + b).orElse("invalid request");
        return ResponseEntity.badRequest().body(ErrorResponse.of("invalid_request", detail));
    }

    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<ErrorResponse> conflict(IllegalStateException e) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(ErrorResponse.of("conflict", e.getMessage()));
    }
}

/**
 * Centralised error classes for the frontend.
 *
 * Classes only define type and statusCode — the message is always
 * provided at the call site or sourced from the API response.
 *
 * Usage:
 *   import { parseApiError, AuthError, NotFoundError } from "@/lib/errors";
 *
 *   try { ... } catch (e) {
 *     const err = parseApiError(e);
 *     if (err instanceof AuthError) router.push("/login");
 *     else toast.error(err.message);
 *   }
 */

// ── Base ───────────────────────────────────────────────────────────────────────

export class AppError extends Error {
  readonly type: string;
  readonly statusCode: number;

  constructor(message: string, type: string, statusCode: number) {
    super(message);
    this.name = this.constructor.name;
    this.type = type;
    this.statusCode = statusCode;
  }
}

// ── 400 Bad Request ────────────────────────────────────────────────────────────

export class ValidationError extends AppError {
  constructor(message: string) {
    super(message, "validation_error", 400);
  }
}

export class ContactFileExpiredError extends AppError {
  constructor(message: string) {
    super(message, "contact_file_expired", 400);
  }
}

export class InvalidFileFormatError extends AppError {
  constructor(message: string) {
    super(message, "invalid_file_format", 400);
  }
}

// ── 401 Unauthorized ───────────────────────────────────────────────────────────

export class AuthError extends AppError {
  constructor(message: string, type = "auth_error") {
    super(message, type, 401);
  }
}

export class InvalidCredentialsError extends AuthError {
  constructor(message: string) {
    super(message, "invalid_credentials");
  }
}

export class InvalidTokenError extends AuthError {
  constructor(message: string) {
    super(message, "invalid_token");
  }
}

export class TokenExpiredError extends AuthError {
  constructor(message: string) {
    super(message, "token_expired");
  }
}

// ── 403 Forbidden ──────────────────────────────────────────────────────────────

export class PermissionError extends AppError {
  constructor(message: string, type = "permission_error") {
    super(message, type, 403);
  }
}

export class AccountDisabledError extends PermissionError {
  constructor(message: string) {
    super(message, "account_disabled");
  }
}

export class InsufficientRoleError extends PermissionError {
  constructor(message: string) {
    super(message, "insufficient_role");
  }
}

// ── 404 Not Found ──────────────────────────────────────────────────────────────

export class NotFoundError extends AppError {
  constructor(message: string) {
    super(message, "not_found", 404);
  }
}

// ── 409 Conflict ───────────────────────────────────────────────────────────────

export class ConflictError extends AppError {
  constructor(message: string, type = "conflict") {
    super(message, type, 409);
  }
}

export class EmailAlreadyExistsError extends ConflictError {
  constructor(message: string) {
    super(message, "email_already_exists");
  }
}

// ── 500 Server Errors ──────────────────────────────────────────────────────────

export class ServerError extends AppError {
  constructor(message: string) {
    super(message, "server_error", 500);
  }
}

// ── Error type map (backend `type` → frontend class) ──────────────────────────

const ERROR_TYPE_MAP: Record<string, new (message: string) => AppError> = {
  validation_error: ValidationError,
  contact_file_expired: ContactFileExpiredError,
  invalid_file_format: InvalidFileFormatError,
  auth_error: AuthError,
  invalid_credentials: InvalidCredentialsError,
  invalid_token: InvalidTokenError,
  token_expired: TokenExpiredError,
  permission_error: PermissionError,
  account_disabled: AccountDisabledError,
  insufficient_role: InsufficientRoleError,
  not_found: NotFoundError,
  campaign_not_found: NotFoundError,
  user_not_found: NotFoundError,
  template_not_found: NotFoundError,
  conflict: ConflictError,
  email_already_exists: EmailAlreadyExistsError,
  server_error: ServerError,
  redis_error: ServerError,
  whatsapp_api_error: ServerError,
};

/**
 * Converts any thrown value (axios error, plain Error, unknown) into a typed
 * AppError subclass. Safe to use in every catch block.
 */
function fromApiResponse(response: any): AppError {
  const { detail, type } = response.data ?? {};
  const status = response.status ?? 500;
  const message = detail ?? "An unexpected error occurred";

  if (type && ERROR_TYPE_MAP[type]) return new ERROR_TYPE_MAP[type](message);

  switch (status) {
    case 400:
      return new ValidationError(message);
    case 401:
      return new AuthError(message);
    case 403:
      return new PermissionError(message);
    case 404:
      return new NotFoundError(message);
    case 409:
      return new ConflictError(message);
    default:
      return new ServerError(message);
  }
}

function fromNativeError(err: any): AppError {
  if (err instanceof AppError) return err;
  return new ServerError(err instanceof Error ? err.message : "An unexpected error occurred");
}

export function parseApiError(err: unknown): AppError {
  const response = (err as any)?.response;
  if (response) return fromApiResponse(response);
  return fromNativeError(err);
}

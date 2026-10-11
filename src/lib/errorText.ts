// The message of a service error (services already turn API failures into readable
// text), or the caller's fallback when there is none.
export const errorText = (error: unknown, fallback: string) => error instanceof Error && error.message ? error.message : fallback

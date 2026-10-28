/**
 * Public entry point of @multiverse/contracts. Other modules import only from here,
 * never from src/generated directly (ADR-0009).
 */
export type * from "./generated/contracts";
export { CONTRACTS_VERSION } from "./generated/version";

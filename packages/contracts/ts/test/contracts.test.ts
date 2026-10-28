import { describe, expect, expectTypeOf, it } from "vitest";
import { CONTRACTS_VERSION } from "@multiverse/contracts";
import type {
  MetricValue,
  ReproducibilityManifest,
  ResultMode,
  ValueKind,
} from "@multiverse/contracts";

describe("@multiverse/contracts", () => {
  it("exposes the contracts version generated from the schema", () => {
    expect(CONTRACTS_VERSION).toMatch(/^\d+\.\d+\.\d+$/);
  });

  it("models value kinds and result modes as closed unions", () => {
    expectTypeOf<ValueKind>().toEqualTypeOf<"observed" | "forecast" | "simulated">();
    expectTypeOf<ReproducibilityManifest["mode"]>().toEqualTypeOf<ResultMode>();
  });

  it("keeps money as a decimal string", () => {
    const revenue = {
      metric: "revenue",
      quantity: { value: "4213587912", unit: "currency", currency: "USD" },
      kind: "observed",
      data_origin: "synthetic",
      period: {
        type: "fiscal_quarter",
        end_date: "2022-12-31",
        fiscal_year: 2022,
        fiscal_quarter: 4,
      },
      as_of: "2023-02-15T00:00:00Z",
    } satisfies MetricValue;

    expectTypeOf<NonNullable<MetricValue["quantity"]>["value"]>().toEqualTypeOf<string>();
    expect(revenue.quantity.value).toBe("4213587912");

    const notMoney: MetricValue["quantity"] = {
      // @ts-expect-error money is never a JSON number
      value: 4213587912,
      unit: "currency",
      currency: "USD",
    };
    expect(notMoney).toBeDefined();
  });

  it("requires missing values to be explicit nulls", () => {
    expectTypeOf<null>().toExtend<MetricValue["quantity"]>();
  });
});

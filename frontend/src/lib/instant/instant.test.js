import { describe, expect, it } from "vitest";
import { calculate } from "./calc.js";
import { instantAnswer } from "./index.js";
import { convertUnits } from "./units.js";

const calc = (s) => calculate(s)?.value;

describe("calculator", () => {
  it.each([
    ["2+2", 4],
    ["2 + 3 * 4", 14],
    ["(2 + 3) * 4", 20],
    ["2^10", 1024],
    ["2**10", 1024],
    ["2^3^2", 512],
    ["-2^2", -4],
    ["10 / 4", 2.5],
    ["10 mod 3", 1],
    ["5!", 120],
    ["50%", 0.5],
    ["20% of 150", 30],
    ["sqrt(16) + 1", 5],
    ["√16", 4],
    ["sqrt 16", 4],
    ["2pi", 2 * Math.PI],
    ["π*2", 2 * Math.PI], // broken in v1 (became math.math.pi)
    ["pi", Math.PI],
    ["3(4+5)", 27],
    ["ln(e)", 1],
    ["log(1000)", 3],
    ["sin(30deg)", 0.5],
    ["1e3 + 1", 1001],
    ["3 × 4 ÷ 2", 6],
    ["what is 6*7", 42],
  ])("%s = %d", (input, expected) => {
    expect(calc(input)).toBeCloseTo(expected, 10);
  });

  it.each([
    "",
    "2024",
    "3.12",
    "e",
    "python 3",
    "2 3",
    "hello world",
    "1/0",
    "9^9^9^9",
    "200!",
    "().__class__",
    "ln(1)+().__class__.__base__",
    "constructor",
    "x".repeat(300),
    "sin",
    "(2+3",
  ])("rejects %j", (input) => {
    expect(calculate(input)).toBeNull();
  });

  it("formats results", () => {
    expect(calculate("1000*1000").result).toBe("1,000,000");
    expect(calculate("1/3").result).toBe("0.333333333333");
    expect(calculate("0.1+0.2").result).toBe("0.3");
  });
});

describe("unit conversion", () => {
  it.each([
    ["10 km in miles", 6.2137119224],
    ["1 mile to km", 1.609344],
    ["100 c to f", 212],
    ["32 f in celsius", 0],
    ["0 c to k", 273.15],
    ["1 kg to lb", 2.2046226218],
    ["1 gb in mb", 1000],
    ["1 gib in mib", 1024],
    ["60 mph to km/h", 96.56064],
    ["1 cup in ml", 236.5882365],
    ["2 hours in minutes", 120],
    ["5 ft in m", 1.524],
    ["10 in to cm", 25.4],
    ["1,000 m to km", 1],
  ])("%s", (input, expected) => {
    expect(convertUnits(input).value).toBeCloseTo(expected, 6);
  });

  it.each(["10 km in kg", "km to miles", "10 apples to oranges", "python in production"])("rejects %j", (input) => {
    expect(convertUnits(input)).toBeNull();
  });

  it("rounds results sensibly", () => {
    expect(convertUnits("10 km in miles").result).toBe("6.213712 mi");
    expect(convertUnits("100 c to f").result).toBe("212 °F");
  });

  it("is preferred over the calculator", () => {
    expect(instantAnswer("10 km to m").type).toBe("conversion");
    expect(instantAnswer("10 * 3").type).toBe("calculation");
    expect(instantAnswer("best pizza")).toBeNull();
  });
});

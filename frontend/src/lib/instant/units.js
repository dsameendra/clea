// Unit conversion: "10 km in miles", "72 f to c", "1.5 gb in mib", "60 mph to km/h".

import { formatNumber } from "./calc.js";

// factor = how many base units one of this unit is.
const DIMENSIONS = {
  length: {
    base: "m",
    units: {
      mm: [0.001, "millimetres", "millimeter", "millimeters", "millimetre"],
      cm: [0.01, "centimetres", "centimeter", "centimeters", "centimetre"],
      m: [1, "metres", "meter", "meters", "metre"],
      km: [1000, "kilometres", "kilometer", "kilometers", "kilometre", "kms"],
      in: [0.0254, "inches", "inch", "\""],
      ft: [0.3048, "feet", "foot", "'"],
      yd: [0.9144, "yards", "yard", "yds"],
      mi: [1609.344, "miles", "mile"],
      nmi: [1852, "nautical miles", "nautical mile"],
      ly: [9.4607e15, "light years", "light year", "lightyears"],
    },
  },
  mass: {
    base: "kg",
    units: {
      mg: [1e-6, "milligrams", "milligram"],
      g: [0.001, "grams", "gram", "gr"],
      kg: [1, "kilograms", "kilogram", "kilo", "kilos", "kgs"],
      t: [1000, "tonnes", "tonne", "metric tons", "metric ton"],
      oz: [0.028349523125, "ounces", "ounce"],
      lb: [0.45359237, "pounds", "pound", "lbs"],
      st: [6.35029318, "stone", "stones"],
    },
  },
  volume: {
    base: "l",
    units: {
      ml: [0.001, "millilitres", "milliliter", "milliliters", "millilitre"],
      l: [1, "litres", "liter", "liters", "litre"],
      tsp: [0.00492892159375, "teaspoons", "teaspoon"],
      tbsp: [0.01478676478125, "tablespoons", "tablespoon"],
      "fl oz": [0.0295735295625, "fluid ounces", "fluid ounce", "floz"],
      cup: [0.2365882365, "cups"],
      pt: [0.473176473, "pints", "pint"],
      qt: [0.946352946, "quarts", "quart"],
      gal: [3.785411784, "gallons", "gallon"],
      "m³": [1000, "m3", "cubic metres", "cubic meters", "cubic metre", "cubic meter"],
    },
  },
  time: {
    base: "s",
    units: {
      ms: [0.001, "milliseconds", "millisecond"],
      s: [1, "seconds", "second", "sec", "secs"],
      min: [60, "minutes", "minute", "mins"],
      h: [3600, "hours", "hour", "hr", "hrs"],
      day: [86400, "days", "d"],
      week: [604800, "weeks", "wk"],
      year: [31557600, "years", "yr", "yrs"],
    },
  },
  data: {
    base: "B",
    units: {
      bit: [0.125, "bits"],
      B: [1, "bytes", "byte"],
      kB: [1e3, "kb", "kilobytes", "kilobyte"],
      MB: [1e6, "mb", "megabytes", "megabyte"],
      GB: [1e9, "gb", "gigabytes", "gigabyte"],
      TB: [1e12, "tb", "terabytes", "terabyte"],
      KiB: [1024, "kib", "kibibytes"],
      MiB: [1024 ** 2, "mib", "mebibytes"],
      GiB: [1024 ** 3, "gib", "gibibytes"],
      TiB: [1024 ** 4, "tib", "tebibytes"],
    },
  },
  speed: {
    base: "m/s",
    units: {
      "m/s": [1, "mps", "metres per second", "meters per second"],
      "km/h": [1 / 3.6, "kph", "kmh", "kmph", "kilometres per hour", "kilometers per hour"],
      mph: [0.44704, "miles per hour"],
      kn: [0.514444, "knots", "knot", "kt"],
      "ft/s": [0.3048, "fps", "feet per second"],
    },
  },
  area: {
    base: "m²",
    units: {
      "m²": [1, "m2", "sq m", "square metres", "square meters"],
      "km²": [1e6, "km2", "sq km", "square kilometres", "square kilometers"],
      "ft²": [0.09290304, "ft2", "sq ft", "square feet"],
      ha: [1e4, "hectares", "hectare"],
      acre: [4046.8564224, "acres"],
    },
  },
};

const TEMPERATURE = {
  "°C": ["c", "celsius", "°c", "degc", "centigrade"],
  "°F": ["f", "fahrenheit", "°f", "degf"],
  K: ["k", "kelvin", "kelvins"],
};

const LOOKUP = new Map();
for (const [dimension, { units }] of Object.entries(DIMENSIONS)) {
  for (const [symbol, [factor, ...aliases]] of Object.entries(units)) {
    for (const name of [symbol, ...aliases]) {
      // Data units are case-sensitive for b/B only; everything else is case-insensitive.
      const key = dimension === "data" && (name === "B" || name === "bit") ? name : name.toLowerCase();
      if (!LOOKUP.has(key)) LOOKUP.set(key, { dimension, symbol, factor });
    }
  }
}
for (const [symbol, aliases] of Object.entries(TEMPERATURE)) {
  for (const name of [symbol, ...aliases]) LOOKUP.set(name.toLowerCase(), { dimension: "temperature", symbol });
}

function findUnit(raw) {
  const name = raw.trim().replace(/\s+/g, " ").replace(/^degrees? /i, "");
  return LOOKUP.get(name) || LOOKUP.get(name.toLowerCase()) || null;
}

function toKelvin(v, unit) {
  if (unit === "°C") return v + 273.15;
  if (unit === "°F") return (v - 32) * (5 / 9) + 273.15;
  return v;
}

function fromKelvin(v, unit) {
  if (unit === "°C") return v - 273.15;
  if (unit === "°F") return (v - 273.15) * (9 / 5) + 32;
  return v;
}

const PATTERN = /^\s*(?:convert\s+)?(-?\d[\d,]*(?:\.\d+)?(?:e[+-]?\d+)?|-?\.\d+)\s*([^\d\s].*?)\s+(?:in|to|into|as|=|->|→)\s+(.+?)\s*\??\s*$/i;

export function convertUnits(input) {
  const m = PATTERN.exec(input || "");
  if (!m) return null;
  const value = parseFloat(m[1].replace(/,/g, ""));
  const from = findUnit(m[2]);
  const to = findUnit(m[3]);
  if (!from || !to || from.dimension !== to.dimension || !Number.isFinite(value)) return null;
  let result;
  if (from.dimension === "temperature") {
    result = fromKelvin(toKelvin(value, from.symbol), to.symbol);
  } else {
    result = (value * from.factor) / to.factor;
  }
  if (!Number.isFinite(result)) return null;
  return {
    type: "conversion",
    dimension: from.dimension,
    expression: `${formatNumber(value)} ${from.symbol}`,
    result: `${formatNumber(result, 7)} ${to.symbol}`,
    value: result,
  };
}

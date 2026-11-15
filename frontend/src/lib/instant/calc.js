// A small, safe calculator: tokenizer + Pratt parser. No eval/Function.
//
// Supports + - * / ^ ** mod, % (percent), "x% of y", ! (factorial), parentheses,
// implicit multiplication (2pi, 3(4+5)), constants (pi π e tau φ) and functions
// (sqrt √ cbrt sin cos tan asin acos atan ln log log2 exp abs floor ceil round).
// Angles are radians; append "deg" or "°" for degrees: sin(30deg).

const MAX_INPUT = 200;
const MAX_FACTORIAL = 170;

const CONSTANTS = { pi: Math.PI, "π": Math.PI, e: Math.E, tau: 2 * Math.PI, phi: (1 + Math.sqrt(5)) / 2, "φ": (1 + Math.sqrt(5)) / 2 };
const FUNCTIONS = {
  sqrt: Math.sqrt, "√": Math.sqrt, cbrt: Math.cbrt, sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan, sinh: Math.sinh, cosh: Math.cosh, tanh: Math.tanh,
  ln: Math.log, log: Math.log10, log10: Math.log10, log2: Math.log2, exp: Math.exp, abs: Math.abs,
  floor: Math.floor, ceil: Math.ceil, round: Math.round,
};

class CalcError extends Error {}

function tokenize(input) {
  const tokens = [];
  const src = input.replace(/[×✕]/g, "*").replace(/[÷]/g, "/").replace(/[−–]/g, "-").replace(/\*\*/g, "^");
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (/\s/.test(ch)) { i++; continue; }
    const num = /^(\d+(?:[.,]\d+)?|\.\d+)(?:e[+-]?\d+)?/i.exec(src.slice(i));
    if (num) {
      tokens.push({ type: "num", value: parseFloat(num[0].replace(",", ".")) });
      i += num[0].length;
      continue;
    }
    const word = /^(?:[a-z]+\d*|π|φ|√|°)/i.exec(src.slice(i));
    if (word) {
      const w = word[0].toLowerCase();
      if (w === "mod") tokens.push({ type: "op", value: "mod" });
      else if (w === "of") tokens.push({ type: "op", value: "of" });
      else if (w === "deg" || w === "degrees" || w === "°") tokens.push({ type: "deg" });
      // A lone "e" is far more likely a search than Euler's number, so it doesn't count as maths on its own.
      else if (w in CONSTANTS) tokens.push({ type: "num", value: CONSTANTS[w], constant: true, counts: w !== "e" });
      else if (w in FUNCTIONS) tokens.push({ type: "fn", value: w });
      else throw new CalcError(`unknown name ${w}`);
      i += word[0].length;
      continue;
    }
    if ("+-*/^%!()".includes(ch)) {
      tokens.push({ type: ch === "(" || ch === ")" ? ch : "op", value: ch });
      i++;
      continue;
    }
    throw new CalcError(`unexpected ${ch}`);
  }
  return tokens;
}

function factorial(n) {
  if (!Number.isInteger(n) || n < 0) throw new CalcError("factorial needs a non-negative integer");
  if (n > MAX_FACTORIAL) return Infinity;
  let r = 1;
  for (let k = 2; k <= n; k++) r *= k;
  return r;
}

const BINARY = {
  "+": [10, (a, b) => a + b],
  "-": [10, (a, b) => a - b],
  "*": [20, (a, b) => a * b],
  "/": [20, (a, b) => { if (b === 0) throw new CalcError("division by zero"); return a / b; }],
  mod: [20, (a, b) => { if (b === 0) throw new CalcError("division by zero"); return ((a % b) + b) % b; }],
  of: [20, (a, b) => a * b],
  "^": [30, (a, b) => Math.pow(a, b)],
};

function parse(tokens) {
  let pos = 0;
  let operators = 0;
  const peek = () => tokens[pos];
  const next = () => tokens[pos++];

  function startsOperand(tok) {
    return tok && (tok.type === "num" || tok.type === "fn" || tok.type === "(");
  }

  function postfix(value) {
    for (;;) {
      const tok = peek();
      if (tok?.type === "op" && tok.value === "!") { next(); operators++; value = factorial(value); }
      else if (tok?.type === "op" && tok.value === "%") { next(); operators++; value = value / 100; }
      else if (tok?.type === "deg") { next(); value = (value * Math.PI) / 180; }
      else return value;
    }
  }

  function primary() {
    const tok = next();
    if (!tok) throw new CalcError("unexpected end");
    if (tok.type === "num") { if (tok.counts) operators++; return postfix(tok.value); }
    if (tok.type === "(") {
      const v = expression(0);
      if (next()?.type !== ")") throw new CalcError("missing )");
      return postfix(v);
    }
    if (tok.type === "fn") {
      operators++;
      const fn = FUNCTIONS[tok.value];
      // sqrt 16, sqrt(16), √16
      const arg = peek()?.type === "(" ? primary() : unary();
      return postfix(fn(arg));
    }
    if (tok.type === "op" && (tok.value === "-" || tok.value === "+")) {
      operators++;
      const v = expression(25); // binds tighter than * but looser than ^ : -2^2 = -4
      return tok.value === "-" ? -v : v;
    }
    throw new CalcError(`unexpected ${tok.value ?? tok.type}`);
  }

  function unary() {
    return primary();
  }

  function expression(minPrec) {
    let left = primary();
    for (;;) {
      const tok = peek();
      if (startsOperand(tok)) {
        // implicit multiplication: 2pi, 3(4+5), 2 sqrt 9
        if (minPrec >= 20) break;
        if (tok.type === "num" && !tok.constant) throw new CalcError("two numbers in a row");
        operators++;
        left = left * expression(20);
        continue;
      }
      if (!tok || tok.type !== "op" || !(tok.value in BINARY)) break;
      const [prec, apply] = BINARY[tok.value];
      if (prec < minPrec || (prec === minPrec && tok.value !== "^")) break;
      next();
      operators++;
      const right = expression(tok.value === "^" ? prec : prec + 1);
      if (tok.value === "^" && Math.abs(right) > 10000) throw new CalcError("exponent too large");
      left = apply(left, right);
    }
    return left;
  }

  const value = expression(0);
  if (pos !== tokens.length) throw new CalcError("unexpected input");
  return { value, operators };
}

export function formatNumber(value, significant = 12) {
  if (Object.is(value, -0)) value = 0;
  if (Number.isInteger(value) && Math.abs(value) < 1e21) return value.toLocaleString("en-US");
  if (Math.abs(value) < 1e21 && Number.isInteger(parseFloat(value.toPrecision(significant)))) {
    return parseFloat(value.toPrecision(significant)).toLocaleString("en-US");
  }
  const abs = Math.abs(value);
  if (abs !== 0 && (abs >= 1e15 || abs < 1e-6)) return value.toExponential(8).replace(/\.?0+e/, "e");
  return parseFloat(value.toPrecision(significant)).toLocaleString("en-US", { maximumFractionDigits: 12 });
}

/** Evaluate ``input``; returns null unless it is a well-formed calculation (not just a number). */
export function calculate(input) {
  const text = (input || "").trim().replace(/=\s*$/, "").replace(/^(what is|calculate|calc)\s+/i, "");
  if (!text || text.length > MAX_INPUT) return null;
  try {
    const tokens = tokenize(text);
    if (!tokens.length) return null;
    const { value, operators } = parse(tokens);
    if (operators === 0 || !Number.isFinite(value)) return null;
    return { type: "calculation", expression: text, value, result: formatNumber(value) };
  } catch (err) {
    if (err instanceof CalcError) return null;
    throw err;
  }
}

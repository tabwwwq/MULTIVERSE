/*
 * Cells of the files people open in a spreadsheet (Stage 24). A text that starts like a formula
 * would run as one there, so it gets a leading apostrophe; a number stays a number, minus sign
 * included. Line breaks in a free text would make a new row, so a heading is kept on one line.
 */

const NUMBER = /^[+-]?\d+(\.\d+)?([eE][+-]?\d+)?$/;
const FORMULA = /^[=+\-@\t\r]/;

export function csvCell(value: string | number): string {
  const text = String(value);
  const safe = !NUMBER.test(text) && FORMULA.test(text) ? `'${text}` : text;
  return /[",\n\r]/.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

/** The text of a `#` comment line: nothing in it can start a new row. */
export function csvNote(value: string): string {
  return value.replace(/[\r\n]+/g, " ");
}

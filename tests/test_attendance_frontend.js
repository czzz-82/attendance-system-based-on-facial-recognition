const fs = require('fs');
const vm = require('vm');
const path = require('path');

function loadAttendanceHelpers() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'app', 'static', 'js', 'attendance.js'), 'utf8');
  const sandbox = {
    console,
    navigator: { mediaDevices: { getUserMedia: async () => ({}) } },
    document: {
      getElementById() {
        return {
          addEventListener() {},
          classList: { add() {}, remove() {} },
          style: {},
          disabled: false,
          textContent: '',
          innerHTML: '',
        };
      },
      querySelector() {
        return { innerHTML: '' };
      },
      createElement() {
        return {
          getContext() {
            return { drawImage() {} };
          },
          toDataURL() {
            return '';
          },
        };
      },
    },
    app: {
      escapeHtml: value => String(value ?? ''),
      api: async () => ({ json: async () => ({ items: [] }) }),
    },
    $: () => ({ textContent: '' }),
    $$: () => [],
    setInterval() { return 1; },
    clearInterval() {},
    alert() {},
    module: { exports: {} },
  };

  vm.runInNewContext(`${source}\nmodule.exports = { formatModelLivenessText };`, sandbox);
  return sandbox.module.exports;
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(`${message}\nExpected: ${expected}\nActual: ${actual}`);
  }
}

const { formatModelLivenessText } = loadAttendanceHelpers();

assertEqual(
  formatModelLivenessText({
    model_liveness_checked: true,
    model_liveness_passed: true,
    model_liveness_score: 0.82,
    model_liveness_reason: 'passed',
  }),
  '模型活体：已通过（0.82）',
  'should format passed model liveness',
);

assertEqual(
  formatModelLivenessText({
    model_liveness_checked: true,
    model_liveness_passed: false,
    model_liveness_score: 0.21,
    model_liveness_reason: 'spoof_detected',
  }),
  '模型活体：未通过（0.21）',
  'should format failed model liveness',
);

assertEqual(
  formatModelLivenessText({
    model_liveness_checked: false,
    model_liveness_passed: null,
    model_liveness_score: null,
    model_liveness_reason: 'dependency_missing',
  }),
  '模型活体：未校验（dependency_missing）',
  'should format skipped model liveness',
);

console.log('attendance frontend helpers OK');

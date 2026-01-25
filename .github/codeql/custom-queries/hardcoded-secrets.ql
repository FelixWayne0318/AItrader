/**
 * @name Hardcoded API keys or secrets
 * @description Detects potential hardcoded API keys, tokens, or secrets in code
 * @kind problem
 * @problem.severity error
 * @security-severity 9.0
 * @id aitrader/hardcoded-secrets
 * @tags security
 *       external/cwe/cwe-798
 */

import python

from StrConst str, string value
where
  value = str.getText() and
  (
    // API key patterns (length > 20 and alphanumeric)
    value.regexpMatch("^[A-Za-z0-9]{20,}$") and
    not value.regexpMatch("^[a-z]+$")  // Exclude all-lowercase words
  )
  or
  (
    // Common secret patterns
    value.regexpMatch("(?i).*(api[_-]?key|api[_-]?secret|password|token|secret[_-]?key)\\s*[=:]\\s*['\"][^'\"]+['\"].*")
  )
  or
  (
    // Binance-like API key format
    value.regexpMatch("^[A-Za-z0-9]{64}$")
  )
  // Exclude test files and configs
  and not str.getLocation().getFile().getRelativePath().matches("%test%")
  and not str.getLocation().getFile().getRelativePath().matches("%.example%")
select str, "Potential hardcoded secret detected: " + value.substring(0, 20) + "..."

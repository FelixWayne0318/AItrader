/**
 * @name Find all import statements
 * @description Lists all import statements in the codebase to track module dependencies
 * @kind problem
 * @problem.severity recommendation
 * @id aitrader/find-imports
 * @tags maintainability
 *       dependency
 */

import python

from ImportingStmt imp, string moduleName
where
  (
    imp instanceof Import and
    moduleName = imp.(Import).getAName().getId()
  )
  or
  (
    imp instanceof ImportStar and
    moduleName = imp.(ImportStar).getModule().getName()
  )
  or
  (
    imp instanceof ImportMember and
    moduleName = imp.(ImportMember).getModule().getName()
  )
select imp, "Import of module: " + moduleName

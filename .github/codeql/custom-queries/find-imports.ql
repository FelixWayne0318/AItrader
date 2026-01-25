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
    exists(Import i, Alias a | i = imp and a = i.getAName() |
      moduleName = a.getAsname().getId()
      or
      not exists(a.getAsname()) and moduleName = a.getValue().(Name).getId()
    )
  )
  or
  (
    imp instanceof ImportStar and
    exists(ImportStar is | is = imp |
      moduleName = is.getModule().(Name).getId()
    )
  )
  or
  (
    imp instanceof ImportMember and
    exists(ImportMember im | im = imp |
      moduleName = im.getModule().(Name).getId()
    )
  )
select imp, "Import of module: " + moduleName

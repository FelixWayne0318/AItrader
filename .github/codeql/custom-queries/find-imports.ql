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
  moduleName = imp.getAnImportedModuleName()
select imp, "Import of module: " + moduleName

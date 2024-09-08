from store import store
from store import stockin
from store import stockout

store.main('http://autotest.local.vpc/api/v1', '')
stockin.main('http://autotest.local.vpc/api/v1', '')
stockout.main('http://autotest.local.vpc/api/v1', '')



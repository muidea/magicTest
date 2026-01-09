from store import store
from store import stockin
from store import stockout

store.main('https://autotest.remote.vpc/api/v1', '')
stockin.main('https://autotest.remote.vpc/api/v1', '')
stockout.main('https://autotest.remote.vpc/api/v1', '')



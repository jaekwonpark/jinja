import requests
from mc_bin_client import MemcachedClient as McdClient

BUCKETS=['server', 'mobile', 'sdk']
MC_HOST="127.0.0.1"
MC_PORT=11210
VIEW_API="http://172.23.121.132:8092/"

for bucket in BUCKETS:

    client = McdClient(MC_HOST, MC_PORT)
    client.sasl_auth_plain(bucket, "")

    DDOC='/'.join([VIEW_API,bucket,'_design',bucket,'_view'])
    PLATFORMS_Q=DDOC+"/all_platforms?stale=false&group_level=1&inclusive_end=true&reduce=true"
    COMPONENTS_Q=DDOC+"/all_components?full_set=true&group_level=1&inclusive_end=true&reduce=true&stale=false"
    BUILDS_Q = DDOC+"/data_by_build?full_set=true&group_level=1&inclusive_end=true&reduce=true&stale=false"

    ALL_PLATFORMS = []
    ALL_COMPONENTS = []

    # all platforms
    r = requests.get(PLATFORMS_Q)
    data = r.json()
    for row in data['rows']:
        platform = row['key']
        ALL_PLATFORMS.append(platform)

    # all components
    r = requests.get(COMPONENTS_Q)
    data = r.json()
    for row in data['rows']:
        component = row['key']
        ALL_COMPONENTS.append(component)


    # purger for all platforms+comonent combo of each build
    r = requests.get(BUILDS_Q)
    data = r.json()
    for row in data['rows']:
        build = row['key'][0]
        if not build:
            continue

        url = DDOC+"/jobs_by_build?startkey=%22"+build+"%22&endkey=%22"+build+"_%22&inclusive_end=true&reduce=false&stale=false"
        r = requests.get(url)
        data = r.json()

        # all jobs
        JOBS = {}
        if not data.get('rows'): continue

        for job in data['rows']:
            _id = str(job['id'])
            val = job['value']
            name = val[0]
            os = val[1]
            comp = val[2]
            cnt = val[5]
            bid = val[6]

            # try to get job url
            url = val[3]
            r = requests.get(url)
            if r.status_code == 404:
                print "****MISSING*** %s_%s: %s:%s:%s (%s,%s)" % (build, _id, os, comp, name, val[5], bid)
                client.delete(_id, vbucket=0)
                continue

            if os in JOBS:
                if comp in JOBS[os]:
                    match = [(i, n) for i, n in enumerate(JOBS[os][comp]) if n[0] == name]
                    if len(match) > 0:
                        idx = match[0][0]
                        oldBid = match[0][1][1]
                        oldDocId = match[0][1][2]
                        if oldBid > bid:
                           # purge this docId because it is less this saved bid
                           client.delete(_id, vbucket=0)
                           print "****PURGE-KEEP*** %s_%s: %s:%s:%s (%s,%s < %s)" % (build, _id, os, comp, name, val[5], bid, oldBid)
                        else:
                           # purge old docId
                           client.delete(oldDocId, vbucket=0)

                           # use this bid as new tracker
                           JOBS[os][comp][idx] = (name, bid, _id)
                           print "****PURGE-REPLACE*** %s_%s: %s:%s:%s (%s,%s > %s)" % (build, _id, os, comp, name, val[5], bid, oldBid)

                        continue
                    else:
                        # append to current comp
                        JOBS[os][comp].append((name,bid, _id))
                else:
                    # new comp
                    JOBS[os][comp] = [(name, bid, _id)]
            else:
                # new os
                JOBS[os] = {}
                JOBS[os][comp] = [(name, bid, _id)]


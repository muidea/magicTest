# 上传文件
参数说明:
1. file: [body(必选)] 文件对象
2. key-name:[query(必选)] file对应的field名
3. fileSouce:[query(必选)] 文件的来源，上传者
4. filePath:[query(可选)] 文件的存储路径,如何指定路径，则存储在指定的路径下，否则按系统默认规则进行存储
4. fileScope:[query(可选)] 文件的所述范围，未传默认为share

# 下载文件
参数说明:
1. fileToken: [query(必选)] 文件token
2. fileSource: [query(可选)] 文件的来源, 如果传入了，则只能下载该来源的文件，否则可以下载相同fileScope下的文件
3. fileScope: [query(可选)] 文件的所述范围，未传入只能下载share的文件

# 查看文件
参数说明:
1. fileToken: [query(必选)] 文件token
2. fileSource: [query(可选)] 文件的来源, 如果传入了，则只能查看该来源的文件，否则可以查看相同fileScope下的文件
3. fileScope: [query(可选)] 文件的所述范围，未传入只能查看share的文件

# 过滤文件清单
参数说明:
1. fileSource: [query(可选)] 文件的来源, 如果传入了，则只能过滤该来源的文件，否则可以过滤相同fileScope下的文件
2. fileScope: [query(可选)] 文件的所述范围，未传入只能过滤share的文件

# 查询文件
参数说明:
1. id: [query(必选)] 文件id
2. fileSource: [query(可选)] 文件的来源, 如果传入了，则只能查看该来源的文件，否则可以查看相同fileScope下的文件
3. fileScope: [query(可选)] 文件的所述范围，未传入只能查看share的文件

# 更新文件&删除文件
参数说明:
1. id: [query(必选)] 文件id
2. fileSource: [query(必选)] 文件的来源, 只有源始者才能更新或删除文件

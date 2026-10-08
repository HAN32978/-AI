"""兼容当前 FAISS 包的元数据谓词；不依赖它是否支持 Chroma 的 $in 字典。"""
def faiss_filter(expression):
    if expression is None or callable(expression):
        return expression
    predicates = []
    for key, expected in expression.items():
        if key in {"$and", "$or"}:
            children = [faiss_filter(child) for child in expected]
            predicates.append(lambda metadata, children=children, op=key: (all if op == "$and" else any)(p(metadata) for p in children))
        elif isinstance(expected, dict):
            if set(expected) == {"$in"}:
                values = set(expected["$in"])
                predicates.append(lambda metadata, k=key, values=values: metadata.get(k) in values)
            elif set(expected) == {"$eq"}:
                predicates.append(lambda metadata, k=key, v=expected["$eq"]: metadata.get(k) == v)
            else:
                raise ValueError("FAISS 元数据过滤包含未支持的操作符")
        else:
            predicates.append(lambda metadata, k=key, v=expected: metadata.get(k) == v)
    return lambda metadata: all(predicate(metadata) for predicate in predicates)

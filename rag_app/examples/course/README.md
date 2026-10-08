# 原课程手动演示脚本

这些文件需要本地模型服务/权重以及自行准备的 sample_docs，属于手动演示，不计入自动化测试。文件已从 tests 迁入本目录，并将含多个点的模块文件改为普通 Python 文件名。

从 rag_app 执行：`python examples/course/module1_config.py`。其余演示可能修改向量库，应使用隔离配置和演示资料。

自动回归：`python -m unittest discover -s tests -p "test_*.py" -v`；真实服务集成脚本在 `integration/verify_workbench.py`。测试层仍需要 requirements 中的依赖；读取 Excel 的路径不再无条件导入 DocumentLoader，但不宣称整个项目可零依赖运行。

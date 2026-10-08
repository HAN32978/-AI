"""
文档加载器模块——支持 pdf word excel txt markdown 等多种格式的文档加载
步骤：
1. 加载文档：使用合适的加载器，可以选择是否添加元数据。 
    什么是元数据？——就是描述数据的数据，例如：文件名、文件类型、作者等等等
    添加元数据，优点就是能更好的管理数据。
2. 分割文档：将文档分割成多个片段，以便于后续的处理。
"""
from pathlib import Path
from config.settings import settings
import logging
logger = logging.getLogger(__name__)
from langchain_community.document_loaders import (
PyMuPDFLoader,
Docx2txtLoader,
TextLoader,
)
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


class ExcelTableLoader:
    """按工作表逐行读取，保留列名、行号，不触发 NLP 资源下载。"""

    def __init__(self, file_path: str):
        self.path = Path(file_path)

    def load(self) -> list:
        import pandas as pd

        engine = "openpyxl" if self.path.suffix.lower() == ".xlsx" else "xlrd"
        documents = []
        with pd.ExcelFile(self.path, engine=engine) as workbook:
            for sheet_name in workbook.sheet_names:
                table = pd.read_excel(workbook, sheet_name=sheet_name, header=None,
                                      dtype=str, keep_default_na=False).fillna("")
                nonempty = table.apply(lambda row: any(str(value).strip() for value in row), axis=1)
                table = table.loc[nonempty]
                if table.empty:
                    continue
                # 工程表格常在第一行合并单元格写标题，下一行才是列名。
                header_index = next((index for index, row in table.iterrows()
                                     if sum(bool(str(value).strip()) for value in row) >= 2), table.index[0])
                title = "；".join(str(value).strip() for _, row in table.loc[table.index < header_index].iterrows()
                                 for value in row if str(value).strip())
                header = [str(value).strip() for value in table.loc[header_index]]
                header_text = " | ".join(value or f"列{index + 1}" for index, value in enumerate(header))
                for row_index, row in table.loc[table.index > header_index].iterrows():
                    cells = [f"{header[index] or f'列{index + 1}'}：{str(value).strip()}"
                             for index, value in enumerate(row) if str(value).strip()]
                    documents.append(Document(
                        page_content=f"工作表：{sheet_name}\n标题：{title}\n表头：{header_text}\nExcel 行号：{row_index + 1}\n" + "；".join(cells),
                        metadata={"sheet_name": sheet_name, "row": int(row_index + 1)},
                    ))
        return documents

class DocumentLoader:
    """统一文档加载器类"""
    # 支持的文档扩展名映射
    LOADER_MAP= {
        ".pdf": PyMuPDFLoader,
        ".docx": Docx2txtLoader,
        ".doc": Docx2txtLoader,
        ".txt": TextLoader,
        ".md": TextLoader,
        ".xlsx": ExcelTableLoader,
        ".xls": ExcelTableLoader
    }

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
            length_function=len
        )

    def load_file(self, file_path: str, metadata: dict = None) -> list:
        """
        加载单个文件
        :param file_path: 文件路径
        :param metadata: 可选的元数据字典
        :return: 文档片段列表
        """
        # 1. 先检查文件是否存在
        file_path = Path(file_path)
        if not file_path.exists():
            logger.error(f"文件不存在: {file_path}")
            return []
        # 2. 检查文件类型
        ext = file_path.suffix.lower()
        if ext not in self.LOADER_MAP:
            logger.error(f"不支持的文件类型: {ext}")
            return []
        try:
            # 3. 加载文档
            loader_class = self.LOADER_MAP[ext]
            if ext in {".txt", ".md"}:
                loader = loader_class(str(file_path), encoding="utf-8")
            else:
                loader = loader_class(str(file_path))
            documents = loader.load()
            logger.info(f"成功加载文件: {file_path}， 原始文档书段数: {len(documents)}")
            # 4. 添加自定义元数据
            base_metadata= {
                "source": str(file_path),
                "file_name": file_path.name,
                "file_type": ext[1:],       # 过滤 .txt 的 . 保留 txt
            }
            if metadata:
                base_metadata.update(metadata)
            for doc in documents:
                doc.metadata.update(base_metadata)
            # 5. 分割文档
            split_docs = self.text_splitter.split_documents(documents)
            logger.info(f"成功分割文档: {file_path}， 分割后的文档数: {len(split_docs)}")
            return split_docs
        except Exception as e:
            logger.error(f"加载文件失败: {file_path}, 错误: {e}")
            return []   

    def load_directory(self, dir_path: str, recursive: bool = True) -> list:
        """
        加载整个目录下的所有文件
        :param dir_path: 目录路径
        :param recursive: 是否递归加载子目录
        :return: 文档片段列表
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            logger.error(f"目录不存在: {dir_path}")
            return []
        # 遍历目录下的所有文件
        all_docs = []
        patten = "**/*" if recursive else "*"
        for file_path in dir_path.rglob(patten):
            if file_path.is_file() and file_path.suffix.lower() in self.LOADER_MAP:
                docs = self.load_file(str(file_path))
                all_docs.extend(docs)
        logger.info(f"成功加载目录: {dir_path}, 共 {len(all_docs)} 个文档片段")
        return all_docs

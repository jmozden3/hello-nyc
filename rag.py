import os
import pickle
import PyPDF2
from langchain_community.embeddings import OpenAIEmbeddings
import faiss
import numpy as np

# Path to store the serialized data
PERSISTENCE_PATH = "./rag_persistence"

if not os.path.exists(PERSISTENCE_PATH):
    os.makedirs(PERSISTENCE_PATH)

# Split the PDF into smaller chunks of text for embeddings
def chunk_pdf(pdf_path, chunk_size=1000):
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = len(reader.pages)
            chunks = []

            for page_num in range(num_pages):
                page = reader.pages[page_num]
                text = page.extract_text()

                # Split the text into chunks
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size]
                    chunks.append(chunk)

            return chunks
    except PyPDF2.errors.PdfReadError as e:
        print(f"Error reading PDF file '{pdf_path}': {e}")
        return []

def augment_prompt(query, embeddings, index, all_chunks, k=5):
    query_embedding = embeddings.embed_query(query)
    query_embedding_np = np.array(query_embedding, dtype="float32").reshape(1, -1)

    D, I = index.search(query_embedding_np, k)
    similar_chunks = [all_chunks[i] for i in I[0]]

    source_knowledge = "\n".join(similar_chunks)
    augmented_prompt = f"""Using the contexts below, answer the query.

    Contexts:
    {source_knowledge}

    Query: {query}"""

    return augmented_prompt

def save_faiss_index(index, filename):
    """Save FAISS index to disk."""
    index_path = os.path.join(PERSISTENCE_PATH, filename)
    faiss.write_index(index, index_path)

def load_faiss_index(filename):
    """Load FAISS index from disk."""
    index_path = os.path.join(PERSISTENCE_PATH, filename)
    if os.path.exists(index_path):
        return faiss.read_index(index_path)
    return None

def save_to_disk(data, filename):
    """Save non-FAISS data (chunks) to disk."""
    with open(os.path.join(PERSISTENCE_PATH, filename), "wb") as f:
        pickle.dump(data, f)

def load_from_disk(filename):
    """Load non-FAISS data (chunks) from disk."""
    try:
        with open(os.path.join(PERSISTENCE_PATH, filename), "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return None

def initialize_rag(rag_folder_path="./static/data", persist=True):
    os.environ["OPENAI_API_KEY"] = ""

    try:
        if persist:
            # Load persisted data
            all_chunks = load_from_disk("all_chunks.pkl")
            index = load_faiss_index("faiss_index.idx")

            if all_chunks and index:
                print("Loaded FAISS index and chunks from disk.")
                embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")
                return embeddings, index, all_chunks

        # Process PDFs to extract chunks
        if not os.path.exists(rag_folder_path):
            raise ValueError(f"The path '{rag_folder_path}' does not exist.")

        files_in_rag_folder = os.listdir(rag_folder_path)
        all_chunks = []
        for filename in files_in_rag_folder:
            if filename.endswith(".pdf"):
                pdf_path = os.path.join(rag_folder_path, filename)
                chunks = chunk_pdf(pdf_path)
                all_chunks.extend(chunks)

        print(f"Total number of chunks created from all PDFs: {len(all_chunks)}")

        # Create embeddings and FAISS index
        embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")
        doc_embeddings = embeddings.embed_documents(all_chunks)
        embeddings_np = np.array(doc_embeddings, dtype="float32")

        index = faiss.IndexFlatL2(embeddings_np.shape[1])
        index.add(embeddings_np)

        # Save data to disk
        if persist:
            save_to_disk(all_chunks, "all_chunks.pkl")
            save_faiss_index(index, "faiss_index.idx")

        print("Saved FAISS index and chunks to disk.")
        return embeddings, index, all_chunks

    except Exception as e:
        print(f"Error initializing RAG: {e}")
        return None, None, []

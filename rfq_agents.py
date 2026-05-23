
# import os
# import re
# import json
# import uuid
# import base64
# import pandas as pd
# from email.mime.text import MIMEText
# from langgraph.graph import StateGraph, END
# from langchain_openai import ChatOpenAI
# from langchain.prompts import ChatPromptTemplate
# from sqlalchemy.orm import sessionmaker
# from app.database.DatabaseOperationPostgreSQL import Session
# import logging
# from Tools.GmailTool import GmailTool  #
# from app.models.suppliers_details import SupplierDetails 
# from typing import List, Dict, Any, Optional
# from pydantic import BaseModel

# class RFQState(BaseModel):
#     folder: Optional[str] = None          # Input: rfq_folder path
#     output_path: Optional[str] = None     # Path to universal RFQ Excel
#     input_path: Optional[str] = None      # Path for next stage input
#     result: Optional[str] = None          # Message/summary
#     emails: Optional[List[Dict[str, Any]]] = None  # Emails prepared/sent

# class RFQProcessor:
#     def __init__(self, input_folder: str,credentials_file: str = "client_secret.json",token_file: str = "token.json"):
#         """Initialize RFQProcessor with rfq_folder and setup LLM."""
#         self.state = RFQState(folder=input_folder)
#         self.credentials_file = credentials_file
#         self.token_file = token_file
#         self.llm = ChatOpenAI(model="gpt-4o", temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))
#         self.extraction_prompt = ChatPromptTemplate.from_template(
#             """You are an information extraction assistant.
#             From the following purchase order / RFQ content, extract and normalize the data
#             into a fixed JSON schema.

#             Rules:
#             - Always follow the exact schema below.
#             - If a field is missing, still include the key with value "".
#             - "Line Items" must always be a list.
#             - Extract UOM from the "Quantity (Unit)" if available.
#             - Normalize numbers where possible.

#             Output format:
#             {{
#             "Line Items": [
#                 {{
#                 "Line Seq": "...",
#                 "Item": "...",
#                 "Description": "...",
#                 "Material Spec": "...",
#                 "Qty": "...",
#                 "UOM": "...",
#                 "Make": "...",
#                 "Part No": "...",
#                 "Notes": "..."
#                 }}
#             ]
#             }}

#             Content:
#             {content}
#             """
#         )
#         self.output_folder = os.path.join(self.state.folder, "output")
#         self.input_subfolder = os.path.join(self.state.folder, "input")  # Added for input subfolder
#         os.makedirs(self.output_folder, exist_ok=True)
#         self.workflow = self._build_workflow()
        
#     gmail = GmailTool(
#         credentials_file="client_secret.json",  # your Google API client secret JSON
#         token_file="token.json",                # where your token will be stored
#         auth_mode="local",                      # "local" or "manual"
#         local_server_port=8080                  # optional: port for local server
#     )
#     def _safe_json_parse(self, raw_output: str) -> Dict:
#         """Parse JSON output safely, handling potential formatting issues."""
#         try:
#             cleaned = raw_output.strip()
#             cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
#             cleaned = re.sub(r"```$", "", cleaned).strip()
#             cleaned = re.sub(r"^[^{\[]+", "", cleaned)
#             cleaned = re.sub(r"[^}\]]+$", "", cleaned)
#             return json.loads(cleaned)
#         except Exception as e:
#             logger.error(f"JSON parsing error: {e}")
#             return {"raw_output": raw_output}

#     def _send_gmail_message(self, to: str, subject: str, body: str, content_type: str = "html") -> Dict:
#         """Send email via Gmail API."""
#         service = gmail.authenticate()
#         message = MIMEText(body, content_type)
#         message["to"] = to
#         message["from"] = "ankita.combat@gmail.com"
#         message["subject"] = subject
#         raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
#         msg = {"raw": raw}
#         return service.users().messages().send(userId="me", body=msg).execute()

#     def _rfq_agent_process(self, content: str, source_ref: str) -> Dict:
#         """Process RFQ content using LLM to extract data."""
#         chain = self.extraction_prompt | self.llm
#         response = chain.invoke({"content": content})
#         parsed = self._safe_json_parse(response.content)
#         return {
#             "Line Items": parsed.get("Line Items", []),
#             "Source": "JSON",
#             "Source Ref": source_ref,
#         }

#     def _excel_to_json(self, path: str) -> Dict:
#         """Convert Excel file to JSON format."""
#         df = pd.read_excel(path)
#         df = df.rename(
#             columns={
#                 "Sr.No.": "Line Seq",
#                 "Item": "Item",
#                 "Description": "Description",
#                 "Make": "Make",
#                 "Part no.": "Part No",
#                 "Reqd Qty": "Qty",
#                 "UOM": "UOM",
#             }
#         )
#         df["Material Spec"] = ""
#         df["Notes"] = ""
#         df = df[
#             [
#                 "Line Seq",
#                 "Item",
#                 "Description",
#                 "Material Spec",
#                 "Qty",
#                 "UOM",
#                 "Make",
#                 "Part No",
#                 "Notes",
#             ]
#         ]
#         return {
#             "Line Items": df.to_dict(orient="records"),
#             "Source": "Excel",
#             "Source Ref": os.path.basename(path),
#         }

#     def _build_universal_excel(self, inputs: List[Dict], output_path: str) -> str:
#         """Build universal RFQ Excel from processed inputs."""
#         all_rows = []
#         for rfq in inputs:
#             rfq_id = str(uuid.uuid4())
#             for item in rfq["Line Items"]:
#                 all_rows.append(
#                     {
#                         "RFQ_ID": rfq_id,
#                         "Line Seq": item.get("Line Seq", ""),
#                         "Item": item.get("Item", ""),
#                         "Description": item.get("Description", ""),
#                         "Material Spec": item.get("Material Spec", ""),
#                         "Qty": item.get("Qty", ""),
#                         "UOM": item.get("UOM", ""),
#                         "Make": item.get("Make", ""),
#                         "Part No": item.get("Part No", ""),
#                         "Notes": item.get("Notes", ""),
#                         "Source": rfq.get("Source", ""),
#                         "Source Ref": rfq.get("Source Ref", ""),
#                         "Supplier(s)": "",
#                         "Supplier Email(s)": "",
#                     }
#                 )
#         df = pd.DataFrame(all_rows)
#         df.to_excel(output_path, index=False)
#         return output_path

#     def rfq_folder_agent(self, state: dict) -> Dict:
#         """Process RFQ files in the rfq_folder and create universal Excel."""
#         inputs = []
#         json_path = os.path.join(self.state.folder, "rfq.json")  # Look for rfq.json in rfq_folder
#         if os.path.exists(json_path):
#             try:
#                 with open(json_path, "r", encoding="utf-8") as f:
#                     data = json.load(f)
#                 # Process email_text
#                 email_text = data.get("email_text", "")
#                 if email_text.strip():
#                     inputs.append(self._rfq_agent_process(email_text, "rfq.json:email_text"))
#                 # Process each pdf_text entry
#                 pdf_texts = data.get("pdf_text", [])
#                 for pdf_entry in pdf_texts:
#                     pdf_text = pdf_entry.get("text", "")
#                     pdf_file = pdf_entry.get("file", "unknown_pdf")
#                     if pdf_text.strip():
#                         inputs.append(self._rfq_agent_process(pdf_text, f"rfq.json:pdf_text:{pdf_file}"))
#             except Exception as e:
#                 logger.error(f"Failed to process JSON {json_path}: {e}")

#         # Process Excel files in the input subfolder
#         input_folder = self.input_subfolder
#         if os.path.exists(input_folder):
#             for file in os.listdir(input_folder):
#                 if file.startswith("~$"):
#                     continue
#                 fpath = os.path.join(input_folder, file)
#                 if file.lower().endswith((".xls", ".xlsx")):
#                     try:
#                         inputs.append(self._excel_to_json(fpath))
#                     except Exception as e:
#                         logger.error(f"Failed to process Excel {file}: {e}")

#         output_path = os.path.join(self.output_folder, "Universal_RFQ.xlsx")
#         self.state.output_path = output_path
#         path = self._build_universal_excel(inputs, output_path)
#         self.state.input_path = path
#         return {"result": f"Universal RFQ saved to {path}", "output_path": output_path, "input_path": path}

#     def supplier_matching_agent(self, state: dict) -> Dict:
#         """Match suppliers to RFQ items and update Excel."""
#         universal_path = state.get("output_path", os.path.join(self.output_folder, "Universal_RFQ.xlsx"))
#         df = pd.read_excel(universal_path)
#         session = SessionLocal()

#         for idx, row in df.iterrows():
#             item_code = str(row.get("Item", "")).strip()
#             description = str(row.get("Description", "")).lower()
#             material_spec = str(row.get("Material Spec", "")).lower()
#             notes = str(row.get("Notes", "")).lower()
#             make = str(row.get("Make", "")).strip()

#             suppliers = []
#             query = (
#                 session.query(Supplier)
#                 .filter(Supplier.item_code == item_code, Supplier.active_flag == True)
#                 .all()
#             )
#             if make:
#                 query = [s for s in query if make.lower() in (s.supplier or "").lower()]
#             if not query:
#                 query = session.query(Supplier).filter(Supplier.active_flag == True).all()
#                 query = [
#                     s
#                     for s in query
#                     if any(
#                         kw.strip().lower() in (description + material_spec + notes)
#                         for kw in (s.material_description or "").split(",")
#                     )
#                 ]
#             for s in query:
#                 suppliers.append((s.supplier, s.supplier_email))
#             if suppliers:
#                 df["Supplier(s)"] = df["Supplier(s)"].astype("string")
#                 df["Supplier Email(s)"] = df["Supplier Email(s)"].astype("string")
#                 df.at[idx, "Supplier(s)"] = "; ".join([s[0] for s in suppliers])
#                 df.at[idx, "Supplier Email(s)"] = "; ".join([s[1] for s in suppliers])

#         session.close()
#         updated_path = os.path.join(self.output_folder, "Universal_RFQ_with_suppliers.xlsx")
#         df.to_excel(updated_path, index=False)
#         self.state.input_path = updated_path
#         return {"result": f"Supplier-mapped RFQ saved to {updated_path}", "input_path": updated_path}

#     def rfq_email_agent(self, state: dict) -> Dict:
#         """Send RFQ emails to suppliers with an HTML table and save email details."""
#         universal_path = state.get("input_path", os.path.join(self.output_folder, "Universal_RFQ_with_suppliers.xlsx"))
#         df = pd.read_excel(universal_path)
#         emails_to_send = []

#         for (supplier, supplier_email), group in df.groupby(["Supplier(s)", "Supplier Email(s)"]):
#             if not supplier_email or pd.isna(supplier_email):
#                 continue

#             # Build HTML email body
#             html_body = f"""
#             <html>
#                 <head>
#                     <style>
#                         table {{
#                             border-collapse: collapse;
#                             width: 100%;
#                             font-family: Arial, sans-serif;
#                             margin-top: 20px;
#                         }}
#                         th, td {{
#                             border: 1px solid #dddddd;
#                             text-align: left;
#                             padding: 8px;
#                         }}
#                         th {{
#                             background-color: #f2f2f2;
#                             font-weight: bold;
#                         }}
#                         tr:nth-child(even) {{
#                             background-color: #f9f9f9;
#                         }}
#                         p {{
#                             font-family: Arial, sans-serif;
#                         }}
#                     </style>
#                 </head>
#                 <body>
#                     <p>Dear {supplier},</p>
#                     <p>Please find below the RFQ for the following items:</p>
#                     <table>
#                         <thead>
#                             <tr>
#                                 <th>Item Code</th>
#                                 <th>Description</th>
#                                 <th>Qty</th>
#                                 <th>UOM</th>
#                                 <th>Part No</th>
#                                 <th>Notes</th>
#                             </tr>
#                         </thead>
#                         <tbody>
#             """

#             for _, row in group.iterrows():
#                 html_body += """
#                             <tr>
#                                 <td>{}</td>
#                                 <td>{}</td>
#                                 <td>{}</td>
#                                 <td>{}</td>
#                                 <td>{}</td>
#                                 <td>{}</td>
#                             </tr>
#                 """.format(
#                     row["Item"],
#                     str(row["Description"])[:40],  # Truncate for brevity
#                     row["Qty"],
#                     row["UOM"],
#                     row["Part No"],
#                     str(row["Notes"])[:20]  # Truncate for brevity
#                 )

#             html_body += """
#                         </tbody>
#                     </table>
#                     <p>Kindly provide your quotation at the earliest convenience.</p>
#                     <p>Thank you.</p>
#                 </body>
#             </html>
#             """

#             emails_to_send.append({"supplier": supplier, "email": supplier_email, "body": html_body})
#             try:
#                 self._send_gmail_message(
#                     to=supplier_email,
#                     subject="Request for Quotation (RFQ)",
#                     body=html_body,
#                     content_type="html"
#                 )
#                 logger.info(f"  Email sent to {supplier_email}")
#             except Exception as e:
#                 logger.error(f"❌ Failed to send email to {supplier_email}: {e}")

#         output_path = os.path.join(self.output_folder, "rfq_emails.json")
#         with open(output_path, "w", encoding="utf-8") as f:
#             json.dump(emails_to_send, f, indent=2)

#         return {"result": f"RFQ emails sent and saved to {output_path}", "emails": emails_to_send}

#     def _build_workflow(self) -> StateGraph:
#         """Build and compile the LangGraph workflow."""
#         workflow = StateGraph(dict)
#         workflow.add_node("rfq_folder_agent", self.rfq_folder_agent)
#         workflow.add_node("supplier_matching_agent", self.supplier_matching_agent)
#         workflow.add_node("rfq_email_agent", self.rfq_email_agent)
#         workflow.set_entry_point("rfq_folder_agent")
#         workflow.add_edge("rfq_folder_agent", "supplier_matching_agent")
#         workflow.add_edge("supplier_matching_agent", "rfq_email_agent")
#         workflow.add_edge("rfq_email_agent", END)
#         return workflow.compile()

#     def run(self) -> Dict:
#         """Execute the RFQ processing workflow."""
#         return self.workflow.invoke(self.state.dict())
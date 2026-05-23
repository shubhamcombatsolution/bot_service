from flask import Blueprint, request, jsonify
from app.models.llm import LLM
from app.models.basellm import BaseLLM
from app.database.DatabaseOperationPostgreSQL import db_session
import logging
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from  app.routes.helpers.encryption import decrypt_value, encrypt_value,mask_key
from app.services.llm_verification_service import verify_llm_key

llm_blueprint = Blueprint("llm", __name__)

# Set up logger
logger = logging.getLogger(__name__)

# LLM Registration (Protected)
@llm_blueprint.route("/register", methods=["POST"])
@jwt_required()
def create_llm():
    session = next(db_session())
    try:
        # ✅ Extract JWT data
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")

        if not tenant_id:
            return jsonify({
                "status": "error",
                "message": "Unauthorized: Tenant ID missing"
            }), 401

        # ✅ Request data
        data = request.json or {}

        base_llm_id = data.get("base_llm_id")
        llm_secret_key = data.get("llm_secret_key")

        if not base_llm_id or not llm_secret_key:
            return jsonify({
                "status": "error",
                "message": "base_llm_id and llm_secret_key are required"
            }), 400

        # ✅ Validate numeric fields
        try:
            base_llm_id = int(base_llm_id)
        except ValueError:
            return jsonify({"status": "error", "message": "Invalid base_llm_id"}), 400

        try:
            temperature = float(data.get("temperature", 0.7))
            if not (0 <= temperature <= 2):
                raise ValueError
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "Temperature must be between 0 and 2"
            }), 400

        try:
            max_tokens = int(data.get("max_output_tokens", 1024))
        except ValueError:
            return jsonify({
                "status": "error",
                "message": "max_output_tokens must be a number"
            }), 400

        # ✅ Fetch Base LLM (SQLAlchemy 2.0 way)
        base_llm = session.get(BaseLLM, base_llm_id)

        if not base_llm:
            return jsonify({
                "status": "error",
                "message": "Invalid model selected"
            }), 400

        # ✅ Verify API Key
        verification = verify_llm_key(base_llm.base_provider, llm_secret_key)

        if not verification.get("valid"):
            return jsonify({
                "status": "error",
                "message": verification.get("error", "Invalid API key")
            }), 400

        # ✅ Create LLM
        new_llm = LLM(
            base_llm_id=base_llm_id,
            llm_secret_key=encrypt_value(llm_secret_key),
            temperature=temperature,
            max_output_tokens=max_tokens,
            tenant_id=tenant_id,
        )

        session.add(new_llm)
        session.commit()

        return jsonify({
            "status": "success",
            "message": "LLM registered successfully",
            "data": {"llm_id": new_llm.llm_id}
        }), 201

    except Exception as e:
        session.rollback()
        logger.exception(f"Error creating LLM: {str(e)}")

        return jsonify({
            "status": "error",
            "message": "Internal server error"
        }), 500

    finally:
        session.close()

# LLM Update (Protected)
@llm_blueprint.route("/update/<int:llm_id>", methods=["PUT"])
@jwt_required()
def update_llm(llm_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")

        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID not found in token"
            }), 401

        data = request.json or {}

        session = next(db_session())
        try:

            existing_llm = session.query(LLM).filter_by(
                llm_id=llm_id,
                tenant_id=tenant_id,
                del_flg=False
            ).first()

            if not existing_llm:
                return jsonify({
                    "data": {},
                    "status": "error",
                    "message": "LLM not found or unauthorized"
                }), 404


            # -------------------------------
            # base_llm_id validation
            # -------------------------------

            new_base_llm_id = data.get("base_llm_id", existing_llm.base_llm_id)

            try:
                new_base_llm_id = int(new_base_llm_id)
            except (TypeError, ValueError):
                return jsonify({
                    "status": "error",
                    "message": "Invalid base_llm_id"
                }), 400

            base_llm = session.get(BaseLLM, new_base_llm_id)

            if not base_llm:
                return jsonify({
                    "status": "error",
                    "message": "Invalid model selected"
                }), 400

            provider = base_llm.base_provider

            existing_llm.base_llm_id = new_base_llm_id


            # -------------------------------
            # temperature validation
            # -------------------------------

            if "temperature" in data:
                try:
                    temp = float(data["temperature"])
                except (TypeError, ValueError):
                    return jsonify({
                        "status": "error",
                        "message": "Temperature must be between 0 and 2"
                    }), 400

                if temp < 0 or temp > 2:
                    return jsonify({
                        "status": "error",
                        "message": "Temperature must be between 0 and 2"
                    }), 400

                existing_llm.temperature = temp


            # -------------------------------
            # max_output_tokens validation
            # -------------------------------

            if "max_output_tokens" in data:
                try:
                    tokens = int(data["max_output_tokens"])

                    if tokens <= 0:
                        raise ValueError()

                    existing_llm.max_output_tokens = tokens

                except (TypeError, ValueError):
                    return jsonify({
                        "status": "error",
                        "message": "max_output_tokens must be a positive integer"
                    }), 400


            # -------------------------------
            # secret key validation
            # -------------------------------

            if "llm_secret_key" in data:

                if not data["llm_secret_key"]:
                    return jsonify({
                        "status": "error",
                        "message": "llm_secret_key cannot be empty"
                    }), 400

                verification = verify_llm_key(provider, data["llm_secret_key"])

                if not verification["valid"]:
                    return jsonify({
                        "status": "error",
                        "message": verification["error"]
                    }), 400

                existing_llm.llm_secret_key = encrypt_value(data["llm_secret_key"])


            session.commit()

            return jsonify({
                "data": {"llm_id": existing_llm.llm_id},
                "status": "success",
                "message": "LLM updated successfully"
            }), 200


        except Exception as e:
            session.rollback()
            logger.exception(f"Error during LLM update: {str(e)}")

            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error"
            }), 500

        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")

        return jsonify({
            "data": {},
            "status": "error",
            "message": "Internal server error"
        }), 500
        
        
# Get LLM by ID (Protected)
@llm_blueprint.route("/<int:llm_id>", methods=["GET"])
@jwt_required()
def get_llm_by_id(llm_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()  # Access additional claims
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID not found in token"}), 401

        session = next(db_session())
        try:
            llm = session.query(LLM).filter_by(llm_id=llm_id, tenant_id=tenant_id, del_flg=False).first()
            if not llm:
                return jsonify({"data": {}, "status": "error", "message": "LLM not found or unauthorized"}), 404


            return jsonify({
                "data": {
                    "llm_id": llm.llm_id,
                    "base_llm_id": llm.base_llm_id,
                    "provider": llm.base_llm.base_provider,
                    "model_name": llm.base_llm.base_model_name,
                    "model_type": llm.base_llm.base_model_type,
                    "temperature": llm.temperature,
                    "max_output_tokens": llm.max_output_tokens,
                    # "llm_secret_key": mask_key(decrypt_value(llm.llm_secret_key)),
                    "llm_secret_key": decrypt_value(llm.llm_secret_key),
                    "created_at": llm.created_at.isoformat() if llm.created_at else None
                },
                "status": "success",
                "message": "LLM retrieved successfully"
            }), 200
        except Exception as e:
            logger.exception(f"Error fetching LLM by ID: {str(e)}")
            return jsonify({"data": {}, "status": "error", "message": "Internal server error"}), 500
        finally:
            session.close()
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({"data": {}, "status": "error", "message": "Internal server error"}), 500
# Get All LLMs (Protected)

@llm_blueprint.route("/", methods=["POST", "GET"])  # allow POST for webhook/payload
@jwt_required(optional=True)  # allow without JWT
def list_llms():
    try:
        claims = get_jwt() or {}
        token_tenant_id = claims.get("tenant_id")
        role = claims.get("role")

        # Parse payload safely (for POST requests)
        payload = request.get_json(silent=True) or {}
        payload_tenant_id = payload.get("tenant_id")

        # Fallback logic (OR condition)
        tenant_id = token_tenant_id or payload_tenant_id

        if not tenant_id:
            logger.error("Tenant ID missing in both JWT and payload")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Tenant ID missing in both JWT and payload"
            }), 401

        session = next(db_session())
        try:
            llms = session.query(LLM).filter_by(tenant_id=tenant_id, del_flg=False).all()
            def safe_decrypt(value):
                try:
                    return decrypt_value(value)
                except Exception:
                    return ""

            llm_list = [{
                "llm_id": llm.llm_id,
                "base_llm_id": llm.base_llm_id,

                "provider": (llm.base_llm.base_provider if llm.base_llm and llm.base_llm.base_provider else ""),
                "model_name": (llm.base_llm.base_model_name if llm.base_llm and llm.base_llm.base_model_name else ""),
                "model_type": (llm.base_llm.base_model_type if llm.base_llm and llm.base_llm.base_model_type else ""),

                "temperature": llm.temperature,
                "max_output_tokens": llm.max_output_tokens,

                # 🔥 DO NOT DECRYPT HERE
                "llm_secret_key": "************",

                "created_at": llm.created_at.isoformat() if llm.created_at else None
            } for llm in llms]

            return jsonify({
                "data": llm_list,
                "status": "success",
                "message": f"LLMs retrieved successfully for tenant_id={tenant_id}"
            }), 200

        except Exception as e:
            logger.exception(f"Error fetching LLMs: {str(e)}")
            return jsonify({
                "data": {},
                "status": "error",
                "message": "Internal server error while fetching LLMs"
            }), 500
        finally:
            session.close()

    except Exception as e:
        logger.exception(f"Unexpected error in list_llms: {str(e)}")
        return jsonify({
            "data": {},
            "status": "error",
            "message": "Unexpected internal error"
        }), 500

# Delete LLM (Protected)
@llm_blueprint.route("/delete/<int:llm_id>", methods=["DELETE"])
@jwt_required()
def delete_llm(llm_id):
    try:
        identity = get_jwt_identity()
        claims = get_jwt()  # Access additional claims
        tenant_id = claims.get("tenant_id")
        role = claims.get("role")
        if not tenant_id:
            logger.error("Tenant ID not found in token")
            return jsonify({"data": {}, "status": "error", "message": "Tenant ID not found in token"}), 401

        session = next(db_session())
        try:
            llm = session.query(LLM).filter_by(
                        llm_id=llm_id,
                        tenant_id=tenant_id,
                        del_flg=False
                    ).first()
            if not llm:
                return jsonify({"data": {}, "message": "LLM not found or unauthorized", "status": "error"}), 404

            llm.del_flg = True
            session.commit()

            return jsonify({
                "data": {"llm_id": llm.llm_id},
                "message": "LLM deleted successfully",
                "status": "success"
            }), 200
        except Exception as e:
            session.rollback()
            logger.exception(f"Error deleting LLM: {str(e)}")
            return jsonify({"data": {}, "message": str(e), "status": "error"}), 500
        finally:
            session.close()
    except Exception as e:
        logger.exception(f"Unexpected error: {str(e)}")
        return jsonify({"data": {}, "status": "error", "message": "Internal server error"}), 500


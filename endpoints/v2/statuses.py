from app import app
from flask import jsonify
from models.new_events import ChallengeStatus, ChallengeProof

# =========================================
# CHALLENGE PROOFS
# =========================================

@app.route("/v2/statuses/challenges/<challenge_status_id>/proofs", methods=['GET'])
def get_challenge_proofs(challenge_status_id):
    """Get all proofs for a specific challenge status"""
    challenge_status = ChallengeStatus.query.filter_by(id=challenge_status_id).first()
    if not challenge_status:
        return jsonify({'error': 'Challenge status not found'}), 404

    proofs = ChallengeProof.query.filter_by(challenge_status_id=challenge_status_id).all()

    return jsonify({
        'data': [proof.serialize() for proof in proofs],
        'total': len(proofs)
    }), 200

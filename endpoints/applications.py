from app import app, db
from helper.helpers import ModelEncoder
from helper.time_utils import parse_time_to_seconds
from helper.set_discord_role import *
from helper.discord_helper import create_discord_text_channel, set_discord_nickname
from flask import request
from models.models import ClanApplications, Users, RaidTierApplication, RaidTiers, RaidTierLog, ClanRanks, RankApplications
from models.models import DiaryApplications, DiaryTasks, ClanPointsLog, DiaryCompletionLog
from helper.clan_points_helper import increment_clan_points, PointTag
import json, datetime
import logging

@app.route("/applications", methods=['GET'])
def get_applications():
    params = request.args
    filter = params.get('filter')
    if filter is not None:
        applications = ClanApplications.query.filter_by(status=filter).all()
    else:
        applications = ClanApplications.query.all()
    data = []
    for row in applications:
        data.append(row.serialize())
    return data

@app.route("/applications", methods=['POST'])
def create_application():
    data = ClanApplications(**request.get_json())
    if data is None:
        return "No JSON received", 400
    user = Users.query.filter_by(discord_id=data.user_id).first()
    if user and user.is_member and user.is_active:
        return "User is already a member", 400
    application = ClanApplications.query.filter_by(user_id=data.user_id).first()
    if application is not None:
        if application.status == "Pending":
            return "Application already exists and is pending", 400
        elif application.status == "Accepted":
            if user and user.is_member and user.is_active:
                return "User is already a member", 400
            else:
                application.status = "Pending"
                application.verdict_timestamp = None
                application.verdict_reason = None
                db.session.commit()
                add_discord_role(user, "Applied")
                remove_discord_roles(user, ["Guest", "Applicant"])
                return "Application status updated to pending", 200
        elif application.status == "Rejected":
            if (datetime.datetime.now(datetime.timezone.utc) - application.verdict_timestamp).days < 30:
                return "User has been rejected less than 30 days ago", 400

    data.id = None
    data.timestamp = datetime.datetime.now(datetime.timezone.utc)
    db.session.add(data)

    user = Users()
    user.discord_id = data.user_id
    user.runescape_name = data.runescape_name
    user.rank = "Applied"
    user.rank_points = 0
    user.is_member = False
    user.is_admin = False
    user.is_active = True
    user.diary_points = 0
    user.event_points = 0
    user.time_points = 0
    user.event_points = 0
    db.session.add(user)

    db.session.commit()
    add_discord_role(user, "Applied")
    remove_discord_roles(user, ["Guest", "Applicant"])
    set_discord_nickname(user.discord_id, data.runescape_name)
    create_discord_text_channel(channel_name=f"{data.runescape_name}-application", category="Applications", role_name_list=["Staff"], user_id_list=[data.user_id])
    return json.dumps(data.serialize(), cls=ModelEncoder)

@app.route("/applications/<id>", methods=['GET'])
def get_application(id):
    application = ClanApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    return json.dumps(application.serialize(), cls=ModelEncoder)

@app.route("/applications/<id>", methods=['PUT'])
def update_application(id):
    data = ClanApplications(**request.get_json())
    if data is None:
        return "No JSON received", 400
    application = ClanApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    application.runescape_name = data.runescape_name
    application.referral = data.referral
    application.reason = data.reason
    application.goals = data.goals

    db.session.commit()
    return json.dumps(application.serialize(), cls=ModelEncoder)

@app.route("/applications/<id>", methods=['DELETE'])
def delete_application(id):
    application = ClanApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    db.session.delete(application)
    db.session.commit()
    return "Application deleted", 200

@app.route("/applications/<id>/accept", methods=['PUT'])
def accept_application(id):
    application = ClanApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    application.status = "Accepted"
    application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)

    user = Users.query.filter_by(discord_id=application.user_id).first()
    user.rank = "Trialist"
    add_discord_roles(user, ["Trialist", "Member"])
    remove_discord_roles(user, ["Guest", "Applied", "Applicant"])
    user.is_member = True
    user.join_date = datetime.datetime.now(datetime.timezone.utc)

    db.session.commit()
    return "Application accepted", 200

@app.route("/applications/<id>/reject", methods=['PUT'])
def reject_application(id):
    application = ClanApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    application.status = "Rejected"
    body = request.get_json()
    if body is None or "reason" not in body:
        application.reason = "No reason provided"
    else:
        application.reason = body["reason"]
    application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)

    user = Users.query.filter_by(discord_id=application.user_id).first()
    user.rank = "Guest"
    add_discord_role(user, "Guest")
    remove_discord_roles(user, ["Applied", "Applicant"])

    db.session.commit()
    return "Application rejected", 200

@app.route("/applications/diary", methods=['GET'])
def get_applications_diary():
    params = request.args
    filter = params.get('filter')
    discord_id = params.get('discord_id')

    if filter is not None:
        applications = DiaryApplications.query.filter_by(status=filter).all()
    elif discord_id is not None:
        applications = DiaryApplications.query.filter_by(user_id=discord_id).all()
    else:
        applications = DiaryApplications.query.all()

    data = []
    for row in applications:
        data.append(row.serialize())
    return data

@app.route("/applications/diary", methods=['POST'])
def create_application_diary():
    data = DiaryApplications(**request.get_json())
    if data is None:
        return "No JSON received", 400
    user = Users.query.filter_by(discord_id=data.user_id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    diary = DiaryTasks.query.filter_by(diary_shorthand=data.diary_shorthand).all()
    if diary is None or len(diary) == 0:
        return "Could not find Diary", 404

    data.user_id = user.discord_id
    data.runescape_name = user.runescape_name
    data.diary_name = diary[0].diary_name # All diaries with the same shorthand have the same name
    data.timestamp = datetime.datetime.now(datetime.timezone.utc)

    if diary[0].scale is not None:
        try:
            if len(data.party) != int(diary[0].scale):
                return "Party size does not match diary group scale", 400
        except TypeError:
            return "Party was not provided", 400
    if diary[0].diary_time is not None:
        # Find the fastest diary time that the application beats
        fastest_time = None
        succeeded_task = None

        # Parse application time
        data_time_seconds = parse_time_to_seconds(data.time_split)
        if not data_time_seconds:
            return "No time split provided for timed diary task", 400
          
        for task in diary:
            # Parse task time
            task_time_seconds = parse_time_to_seconds(task.diary_time)

            # Compare times in seconds
            if data_time_seconds < task_time_seconds:
                if fastest_time is None or task_time_seconds < fastest_time:
                    fastest_time = task_time_seconds
                    succeeded_task = task

        if succeeded_task is None:
            return "Diary time is not fast enough", 400

        data.target_diary_id = succeeded_task.id
        data.party_ids = []
        for member in data.party:
            # search case insensitive
            member = member.lower()
            # find user by runescape name
            user = Users.query.filter(Users.runescape_name.ilike(member)).first()
            if user is None or not user.is_active:
                data.party_ids.append("")
            else:
                data.party_ids.append(user.discord_id)

        db.session.add(data)
        db.session.commit()

        return json.dumps(data.serialize(), cls=ModelEncoder), 201
    else: # If the diary is not timed, it is a one-off task

        # Check if the user has already completed the diary
        diary_completion = DiaryCompletionLog.query.filter_by(user_id=user.discord_id, diary_id=diary[0].id).first()
        if diary_completion is not None:
            return "Diary already completed", 400
        
        # CA special case
        if diary[0].diary_shorthand in ["elite", "master", "gm"]:
            # Check if the user has already completed a higher tier diary
            # Get the highest tier diary for the user

            diaries_completed = DiaryCompletionLog.query.filter_by(user_id=user.discord_id).all()
            # Get the current highest ca diary tier for the user
            ca_tasks = DiaryTasks.query.filter_by(diary_name="Combat Achievements").all()
            if ca_tasks is None or len(ca_tasks) == 0:
                return "Could not find Combat Achievements diary", 404
            
            # check the diaries_completed for any id that matches in ca_tasks
            highest_ca_progress = None
            highest_points = 0
            tasks = [task.id for task in ca_tasks]
            for completed_diary in diaries_completed:
                if completed_diary.diary_id in tasks and completed_diary.points > highest_points:
                    highest_ca_progress = completed_diary
                    highest_points = completed_diary.points

            # make sure the target diary is higher than the highest ca diary
            if highest_ca_progress is not None:
                if diary[0].diary_points <= highest_ca_progress.points:
                    return "Diary is not higher than current diary", 400
        
        # Check if the user has already applied for the diary
        diary_application = DiaryApplications.query.filter_by(user_id=user.discord_id, target_diary_id=diary[0].id).first()
        if diary_application is not None and diary_application.status == "Pending":
            return "Diary application already pending", 432
        
        data.target_diary_id = diary[0].id
        data.party_ids = []
        for member in data.party:
            # search case insensitive
            member = member.lower()
            # find user by runescape name
            user = Users.query.filter(Users.runescape_name.ilike(member)).first()
            if user is None or not user.is_active:
                data.party_ids.append("")
            else:
                data.party_ids.append(user.discord_id)
        db.session.add(data)
        db.session.commit()

        return json.dumps(data.serialize(), cls=ModelEncoder), 201

@app.route("/applications/diary/<id>", methods=['GET'])
def get_application_diary(id):
    application = DiaryApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    return json.dumps(application.serialize(), cls=ModelEncoder)

@app.route("/applications/diary/<id>", methods=['DELETE'])
def delete_application_diary(id):
    application = DiaryApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    if application.status == "Accepted":
        # Remove diary completion log if application was accepted
        diary_completion = DiaryCompletionLog.query.filter_by(user_id=application.user_id, diary_id=application.target_diary_id).first()
        if diary_completion is not None:
            increment_clan_points(
                user_id=application.user_id,
                points=-diary_completion.points,
                tag=PointTag.DIARY,
                message=f"Diary: {application.diary_shorthand}"
            )
            db.session.delete(diary_completion)
    db.session.delete(application)
    db.session.commit()
    return "Application removed", 200

@app.route("/applications/diary/<id>/accept", methods=['PUT'])
def accept_application_diary(id):
    application = DiaryApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404

    if application.status != "Pending":
        return "Application is not pending", 400

    target_diary = DiaryTasks.query.filter_by(id=application.target_diary_id).first()
    if target_diary is None:
        return "Could not find Diary", 404
    application.status = "Accepted"
    application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)

    update_successful = []
    update_failed = []

    # Grab all of the users in the party
    users = application.party_ids
    if users is None or len(users) == 0:
        users = [application.user_id]

    if len(users) == 1:
        # Check if this is a combat achievement
        ca_shorthands = ["elite", "master", "gm"]
        if target_diary.diary_shorthand in ca_shorthands:
            # Check if the user has already completed the diary
            if DiaryCompletionLog.query.filter_by(user_id=users[0], diary_id=target_diary.id).first() is not None:
                return "Diary already completed", 400

            diaries_completed = DiaryCompletionLog.query.filter_by(user_id=users[0]).all()
            # Get the current highest ca diary tier for the user
            ca_tasks = DiaryTasks.query.filter_by(diary_name="Combat Achievements").all()
            if ca_tasks is None or len(ca_tasks) == 0:
                return "Could not find Combat Achievements diary", 404
            
            # check the diaries_completed for any id that matches in ca_tasks
            highest_ca_progress = None
            highest_points = 0
            tasks = [task.id for task in ca_tasks]
            for diary in diaries_completed:
                if diary.diary_id in tasks and diary.points > highest_points:
                    highest_ca_progress = diary
                    highest_points = diary.points

            # make sure the target diary is higher than the highest ca diary
            if highest_ca_progress is not None:
                if target_diary.diary_points <= highest_ca_progress.points:
                    return "Diary is not higher than current diary", 400
                
            increment_clan_points(
                user_id=users[0],
                points=target_diary.diary_points - highest_points,
                tag=PointTag.DIARY,
                message=f"Diary: {application.diary_shorthand}"
            )

            # approve the application
            new_diary_progress = DiaryCompletionLog()
            new_diary_progress.user_id = users[0]
            new_diary_progress.diary_id = application.target_diary_id
            new_diary_progress.diary_category_shorthand = target_diary.diary_shorthand
            new_diary_progress.party = application.party
            new_diary_progress.party_ids = users
            new_diary_progress.proof = application.proof
            new_diary_progress.points = target_diary.diary_points
            new_diary_progress.time_split = None
            new_diary_progress.timestamp = datetime.datetime.now(datetime.timezone.utc)
            db.session.add(new_diary_progress)
            db.session.commit()
            return "Diary application accepted", 200
            
    for i, user_id in enumerate(users):
        user = Users.query.filter_by(discord_id=user_id).first()
        if user is None:
            update_failed.append(application.party[i])
            continue

        # Grab the fastest diary progress for the user
        # This will be the diary with the fastest time.
        current_diary_progress = DiaryCompletionLog.query.filter_by(user_id=user.discord_id, diary_category_shorthand=application.diary_shorthand).all()
        if current_diary_progress is not None and len(current_diary_progress) > 0:
            current_diary_progress = sorted(current_diary_progress, key=lambda x: parse_time_to_seconds(x.time_split))[0]
        else:
            current_diary_progress = None

        if current_diary_progress is None:
            new_diary_progress = DiaryCompletionLog()
            new_diary_progress.user_id = user_id
            new_diary_progress.diary_id = application.target_diary_id
            new_diary_progress.diary_category_shorthand = target_diary.diary_shorthand
            if application.party is not None:
                new_diary_progress.party = application.party
                new_diary_progress.party_ids = users
            new_diary_progress.proof = application.proof
            new_diary_progress.points = target_diary.diary_points
            new_diary_progress.time_split = application.time_split
            db.session.add(new_diary_progress)

            increment_clan_points(
                user_id=user.discord_id,
                points=target_diary.diary_points,
                tag=PointTag.DIARY,
                message=f"Diary: {application.diary_shorthand}"
            )

            update_successful.append(user_id)
        else:
            # Check to see if the application is faster than the current diary time
            # and faster than the applied diary time
            current_time_seconds = parse_time_to_seconds(current_diary_progress.time_split)
            application_time_seconds = parse_time_to_seconds(application.time_split)
            target_time_seconds = parse_time_to_seconds(target_diary.diary_time)
            if current_time_seconds is None or application_time_seconds is None:
                update_failed.append(user_id)
                continue
            
            if application_time_seconds < current_time_seconds and application_time_seconds < target_time_seconds:
                new_diary_progress = DiaryCompletionLog()
                new_diary_progress.user_id = user_id
                new_diary_progress.diary_id = application.target_diary_id
                new_diary_progress.diary_category_shorthand = target_diary.diary_shorthand
                if application.party is not None:
                    new_diary_progress.party = application.party
                    new_diary_progress.party_ids = users
                new_diary_progress.proof = application.proof
                new_diary_progress.points = target_diary.diary_points
                new_diary_progress.time_split = application.time_split
                db.session.add(new_diary_progress)

                # Get the difference in points between the new diary and the old diary
                current_diary = DiaryTasks.query.filter_by(id=current_diary_progress.diary_id).first()

                if current_diary is not None:
                    points_difference = target_diary.diary_points - current_diary.diary_points
                else:
                    points_difference = 0
                    logging.warning("Could not find current diary for id: " + str(current_diary_progress.diary_id))

                increment_clan_points(
                    user_id=user.discord_id,
                    points=points_difference,
                    tag=PointTag.DIARY,
                    message=f"Diary: {application.diary_shorthand}"
                )

                update_successful.append(user_id)
            else:
                update_failed.append(user_id)
                continue

    db.session.commit()

    return_json = {
        "successful": update_successful,
        "failed": update_failed
    }
    return json.dumps(return_json), 200

@app.route("/applications/diary/<id>/reject", methods=['PUT'])
def reject_application_diary(id):
    application = DiaryApplications.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404

    if application.status != "Pending":
        return "Application is not pending", 400

    application.status = "Rejected"
    body = request.get_json()
    if body is None or "reason" not in body:
        application.reason = "No reason provided"
    else:
        application.reason = body["reason"]
    application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)

    db.session.commit()
    return "Application rejected", 200


@app.route("/applications/raidTier", methods=['GET'])
def get_applications_raid_tier():
    params = request.args
    filter = params.get('filter')
    discord_id = params.get('discord_id')

    if filter is not None:
        applications = RaidTierApplication.query.filter_by(status=filter).all()
    elif discord_id is not None:
        applications = RaidTierApplication.query.filter_by(user_id=discord_id).all()
    else:
        applications = RaidTierApplication.query.all()

    data = []
    for row in applications:
        data.append(row.serialize())
    return data


@app.route("/applications/raidTier", methods=['POST'])
def create_application_raid_tier():
    data = RaidTierApplication(**request.get_json())
    if data is None:
        return "No JSON received", 400
    user = Users.query.filter_by(discord_id=data.user_id).first()
    if user is None or not user.is_active:
        return "Could not find User", 404
    raid_tier = RaidTiers.query.filter_by(id=data.target_raid_tier_id).first()
    if raid_tier is None:
        return "Could not find Raid Tier", 404

    diary_completion = RaidTierLog.query.filter_by(user_id=user.discord_id,
                                                   target_raid_tier_id=str(raid_tier.id)).first()
    if diary_completion is not None:
        return "Raid Tier already Achieved", 400

    current_raid_tier_progress = RaidTierLog.query.filter_by(user_id=user.discord_id,
                                                                tier_name=raid_tier.tier_name).order_by(RaidTierLog.tier_order.desc()).all()
    if len(current_raid_tier_progress) > 0:
        if current_raid_tier_progress[0].tier_order > raid_tier.tier_order:
            return "Already achieved higher raid tier", 400

    # Check if the user has already applied for the Raid Tier
    raid_tier_application = RaidTierApplication.query.filter_by(user_id=user.discord_id,
                                                                target_raid_tier_id=raid_tier.id).first()
    if raid_tier_application is not None and raid_tier_application.status == "Pending":
        return "Diary application already pending", 400

    data.user_id = user.discord_id
    data.runescape_name = user.runescape_name
    data.timestamp = datetime.datetime.now(datetime.timezone.utc)
    data.target_raid_tier_id = raid_tier.id
    db.session.add(data)
    db.session.commit()

    return json.dumps(data.serialize(), cls=ModelEncoder), 201


@app.route("/applications/raidTier/<id>", methods=['GET'])
def get_application_raid_tier(id):
    application = RaidTierApplication.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404
    return json.dumps(application.serialize(), cls=ModelEncoder)


@app.route("/applications/raidTier/<id>/accept", methods=['PUT'])
def accept_application_raid_tier(id):
    application = RaidTierApplication.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404

    if application.status != "Pending":
        return "Application is not pending", 400

    target_raid_tier = RaidTiers.query.filter_by(id=application.target_raid_tier_id).first()
    if target_raid_tier is None:
        return "Could not find Raid Tier", 404
    user = Users.query.filter_by(discord_id=application.user_id).first()
    if user is None:
        return "Could not find User", 400
    current_raid_tier_progress = RaidTierLog.query.filter_by(user_id=user.discord_id,
                                                                tier_name=target_raid_tier.tier_name).order_by(RaidTierLog.tier_order.desc()).all()
    new_raid_log = RaidTierLog()
    new_raid_log.tier_order = target_raid_tier.tier_order
    new_raid_log.tier_name = target_raid_tier.tier_name
    new_raid_log.tier_points = target_raid_tier.tier_points
    new_raid_log.user_id = user.discord_id
    new_raid_log.target_raid_tier_id = target_raid_tier.id


    if len(current_raid_tier_progress) > 0:
        if current_raid_tier_progress[0].tier_order > target_raid_tier.tier_order:
            reject_application_raid_tier(id)
            return "Already completed higher tier", 400
        application.status = "Accepted"
        application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)
        # for each raid tier between the current completed and the target tier, add each tier points to the user
        total_points = 0
        for i in range(current_raid_tier_progress[0].tier_order + 1, target_raid_tier.tier_order + 1):
            tier = RaidTiers.query.filter_by(tier_order=i, tier_name=target_raid_tier.tier_name).first()
            if tier is not None:
                total_points += tier.tier_points

        new_raid_log.tier_points = total_points
        db.session.add(new_raid_log)
        increment_clan_points(
            user_id=user.discord_id,
            points=total_points,
            tag=PointTag.RAID_TIER,
            message=f"Raid Tier: {target_raid_tier.tier_name} {target_raid_tier.tier_order}"
        )
    else:
        application.status = "Accepted"
        application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)
        # add every raid tier points up to the target tier
        total_points = 0
        for i in range(0, target_raid_tier.tier_order + 1):
            tier = RaidTiers.query.filter_by(tier_order=i, tier_name=target_raid_tier.tier_name).first()
            if tier is not None:
                total_points += tier.tier_points
        new_raid_log.tier_points = total_points
        db.session.add(new_raid_log)
        increment_clan_points(
            user_id=user.discord_id,
            points=total_points,
            tag=PointTag.RAID_TIER,
            message=f"Raid Tier: {target_raid_tier.tier_name} {target_raid_tier.tier_order}"
        )

    db.session.commit()
    return "Application accepted", 200


@app.route("/applications/raidTier/<id>/reject", methods=['PUT'])
def reject_application_raid_tier(id):
    application = RaidTierApplication.query.filter_by(id=id).first()
    if application is None:
        return "Could not find Application", 404

    if application.status != "Pending":
        print(application.status)
        return "Application is not pending", 400
    application.status = "Rejected"
    body = request.get_json()
    if body is None or "reason" not in body:
        application.verdict_reason = "No reason provided"
    else:
        application.verdict_reason = body["reason"]
    application.verdict_timestamp = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()
    return "Application rejected", 200

@app.route("/applications/rank/", methods=['GET'])
def get_rank_applications():
    params = request.args
    filter = params.get('filter')
    discord_id = params.get('discord_id')

    if filter is not None:
        applications = RankApplications.query.filter_by(status=filter).all()
    elif discord_id is not None:
        applications = RankApplications.query.filter_by(user_id=discord_id).all()
    else:
        applications = RankApplications.query.all()

    data = []
    for row in applications:
        data.append(row.serialize())
    return data

@app.route("/applications/rank/", methods=['POST'])
def create_rank_application():
    body = request.get_json()
    if body is None:
        return "Invalid request", 400

    # Check to see if user currently has a rank application for this rank
    existing_application = RankApplications.query.filter_by(user_id=body.get("user_id"), rank=body.get("rank")).first()
    if existing_application is not None and existing_application.status == "Pending":
        return "User already has a pending application for this rank", 400
    if existing_application is not None:
        return "User already has an application for this rank", 400

    # Check to see if user is already a member of this rank or higher
    user: Users = Users.query.filter_by(discord_id=body.get("user_id")).first()
    if user is None:
        return "User not found", 404
    if user.rank == body.get("rank") or user.rank_order >= body.get("rank_order"):
        return "User is already a member of this rank or higher", 400
    
    # Check to see if the rank exists
    rank: ClanRanks = ClanRanks.query.filter_by(rank=body.get("rank")).first()
    if rank is None:
        return "Rank not found", 404
    # Get the user's current rank
    user_rank: ClanRanks = ClanRanks.query.filter_by(rank=user.rank).first()
    if rank.rank_order <= user_rank.rank_order:
        return "Rank is lower than current rank", 400
    
    # Check to see if they have the minimum points for the rank
    if user.rank_points < rank.rank_minimum_points:
        return "User does not have enough points for this rank", 400 
    
    # Check to see if the user has been in the clan for the minimum time
    if user.join_date is None:
        return "User has not joined the clan", 400
    
    if (datetime.datetime.now(datetime.timezone.utc) - user.join_date).days < rank.rank_minimum_days:
        return f"Rank requires a minimum of {rank.rank_minimum_days} days in the clan, user has {(datetime.datetime.now(datetime.timezone.utc) - user.join_date).days} days", 400

    application = RankApplications()
    application.user_id = body.get("user_id")
    application.runescape_name = user.runescape_name
    application.desired_rank = body.get("rank")
    application.proof = body.get("proof", [])
    application.status = "Pending"
    application.timestamp = datetime.datetime.now(datetime.timezone.utc)
    db.session.add(application)
    db.session.commit()
    
    return json.dumps(application.serialize(), cls=ModelEncoder), 201

@app.route("/applications/rank/<id>", methods=['GET'])
def get_rank_application(id):
    application = RankApplications.query.filter_by(id=id).first()
    if application is None:
        return "Application not found", 404
    return json.dumps(application.serialize(), cls=ModelEncoder)

@app.route("/applications/rank/<id>/accept", methods=['PUT'])
def accept_rank_application(id):
    # Check if application exists
    application = RankApplications.query.filter_by(id=id).first()
    if application is None:
        return "Application not found", 404
    
    # Check if application is pending
    if application.status != "Pending":
        return "Application is not pending", 400
    
    # Check if user exists
    user = Users.query.filter_by(discord_id=application.user_id).first()
    if user is None:
        return "User not found", 404
    # Check if user is already a member of this rank or higher
    if user.rank == application.rank or user.rank_order >= application.rank_order:
        return "User is already a member of this rank or higher", 400

    # Update application status
    application.status = "Accepted"
    # Set user rank
    old_rank = user.rank
    user.rank = application.rank
    user.rank_order = application.rank_order

    # Remove old rank discord role
    remove_discord_roles(user, [old_rank])
    # Add new rank discord role
    add_discord_roles(user, [user.rank])

    db.session.commit()
    return "Application accepted", 200

@app.route("/applications/rank/<id>/reject", methods=['PUT'])
def reject_rank_application(id):
    # Check if application exists
    application = RankApplications.query.filter_by(id=id).first()
    if application is None:
        return "Application not found", 404

    # Check if application is pending
    if application.status != "Pending":
        return "Application is not pending", 400

    # Update application status
    application.status = "Rejected"
    db.session.commit()
    return "Application rejected", 200

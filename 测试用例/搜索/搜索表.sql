set mapreduce.map.memory.mb=20480;
set mapreduce.reduce.memory.mb=20480;
set mapreduce.map.java.opts='-Xmx9216M';
set mapreduce.reduce.java.opts='-Xmx9216M';

set spark.sql.legacy.charVarcharAsString=true;

set hive.exec.dynamic.partition=true;
set hive.exec.dynamic.partition.mode=nonstrict;
set mapreduce.jobtracker.split.metainfo.maxsize=-1;

add jar viewfs://qunarcluster/user/qhstats/udfs/hive-udf-collections-jar-with-dependencies.jar;
create temporary function get_path_node as 'com.qunar.qhstats.hive.udf.PathNodeObtain';
create temporary function json_map as 'com.qunar.qhstats.hive.udf.json.JsonMapUDF';

add jar viewfs://qunarcluster/user/qhstats/udfs/h_data_hive_udf.jar;
create temporary function search_type as 'com.qunar.interhotel.data.SearchTypeUDF';

add jar viewfs://qunarcluster/user/market/udf/uidmathcer/uidmatch-udf.jar;
create temporary function get_params_tuple as 'com.qunar.qhstats.hive.udf.GenericUDTFParseHotdogTuple';



with tmp_search_list as (
    select
        substr(action_time,1,19) log_datetime,
        substring(action_time,12,2) log_hour,
        log_id,
        platform,
        device_id,
        orig_device_id,
        allotted_id,
        app_id,
        user_id,
        user_name,
        province_name,
        country_name,
        min_price,
        max_price,
        request_type,
        hotel_seq,
        user_hotel_distance,
        hotel_screen_rank,
        qtrace_id,
        is_display,
        is_international,
        search_type,
        (record_start+hotel_screen_rank) rank,
        case when scene_promotion=1 then 1 else 0 end is_ad,
        medal,
        dt,
        service_special_type,
        query,
        query_type,
        case when query is not null then 1 else 0 end as is_query,
        regexp_extract(url, 'searchRoomType=([^&]*)&', 1) as search_hotel_channel,
        regexp_extract(url, 'countryType=([^&]*)&', 1) as country_type,
        get_json_object(regexp_extract(url, 'filterParameterBean=([^&]*)&', 1), '$.channelId') as channel_id,
        regexp_extract(url, 'request_id=([^&]*)&', 1) as search_request_uid,
        regexp_extract(url, 'bizType=([^&]*)&', 1) as biztype,
        case when room_status in (1,2,3) then 0
             when room_status in (5,6,9) then 1
             when room_status in (4) then 2
            end as hotel_status,
        if(search_type=15, 1, 0) as is_recommend,
        app_version,
        search_city_code,
        search_city_name,
        checkin_date,
        checkout_date,
        url,
        record_start,
        nearby_poi_gps,
        hotel_poi_distance,
        recall_type,
        case when nvl(recall_type,'')!='' then sort_array(map_keys(json_map(recall_type))) else null end as recall_key,
        null as is_spider, --是否风控作弊用户
        query_parse,
        t,
        plan_id,
        model_sort,
        origin_sort,
        rerank_sort,
        poi_name,
        poi_type,
        poi_id,
        total_hotels,
        scene_name,
        support_ratio,
        real_business,
        lr,
        compliance_rate,
        display_price,
        hotel_score,
        hotel_comments['total'] as comment_nums,
        suggestType,
        bizVersion,
        cqp,
        qFrom,
        user_gps_city_name,
        query_sort,
        is_filter,
        fromforlog,
        recall_type_recommend,
        pois,
        split(query_hotel_grade,',') as query_hotel_grade,
        location_area_filter,
        comprehensive_filter,
--         todo: add columns
        CASE
            WHEN c_refer_sell_price IS NULL OR price_af_voucher IS NULL THEN NULL
            WHEN cast (c_refer_sell_price as double) < cast( price_af_voucher as double) THEN 0
            WHEN cast (c_refer_sell_price as double) = cast( price_af_voucher as double) THEN 1
            ELSE 2
            END AS is_lose,
        c_refer_sell_price as cpayprice,
        price_af_voucher as qpayprice,
        match_adult as is_partavaliable_price,
        CASE
            WHEN c_refer_sell_price IS NULL OR price_af_voucher IS NULL THEN NULL
            WHEN cast( price_af_voucher as double) - cast (c_refer_sell_price as double)  > 1 THEN 0
            ELSE 1
            END AS is_lose_new,
        ext_map,

        sort_price,
        render_price

    from
        default.dw_ihotel_app_search_rank_list_di
    where dt = ${zdt.addDay(-1).format("yyyyMMdd")}


),
     ihotel_show_dispaly_temp as(
         select
             distinct
             qtrace_id,
             hotel_seq,
             device_id,
             orig_device_id,
             user_name,
             key
         from
             (
                 select
                     case when key in ('hotel/list/GList/ChotelCellView','hotel/list/GList/ChotelCellAvailableView','GList/ChotelCellView','GList/GhotelCellView') then get_json_object(value, '$.traceId')
                          else get_json_object(value, '$.qtraceid') end qtrace_id,

                     case when key in ('hotel/list/GList/ChotelCellAvailableView') then get_json_object(value, '$.hotelSeq')
                          else get_json_object(value, '$.ids')
                         end hotel_seq ,

                     device_id,
                     orig_device_id,
                     user_name,
                     key
                 from dw_qav_hotel_track_info_di
                 where dt = ${zdt.addDay(-1).format("yyyyMMdd")}
                   and key in ('hotel/list/GList/ChotelCellView','hotel/list/GList/ChotelCellAvailableView','GList/ChotelCellView','GList/GhotelCellView')
             ) t where qtrace_id is not null and hotel_seq is not null
     ),
     ihotel_cilck_temp as (
         select
             distinct
             qtrace_id,
             hotel_seq,
             device_id,
             orig_device_id,
             user_name,
             key
         from
             (
                 select
                     get_json_object(value,'$.ext.params.traceId') qtrace_id,
                     get_json_object(value,'$.ext.params.ids')  hotel_seq ,
                     device_id,
                     orig_device_id,
                     user_name,
                     key
                 from dw_qav_hotel_track_info_di
                 where dt = ${zdt.addDay(-1).format("yyyyMMdd")}
                   and key in ('ihotel/GList/GListCard/click/hotelCell')
             ) t where qtrace_id is not null and hotel_seq is not null

     ),
     location_area_filter AS (
         select
             log_id,
             hotel_seq,
             device_id,
             collect_list(
                     map(
                             'filterType', get_json_object(location_area_filter_array, '$.filterType'),
                             'params', get_json_object(location_area_filter_array, '$.params'),
                             'reqParams', get_json_object(location_area_filter_array, '$.reqParams')
                     )
             ) as location_area_filter_array
         from
             (
                 SELECT
                     log_id,
                     hotel_seq,
                     device_id,
                     get_json_object(location_area_filter, concat('$[', pos, ']')) AS location_area_filter_array
                 FROM (
                          SELECT
                              log_id,
                              hotel_seq,
                              device_id,
                              location_area_filter,
                              comprehensive_filter
                          from
                              default.dw_ihotel_app_search_rank_list_di
                          where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
                      ) t
                          LATERAL VIEW posexplode(
                             split(regexp_replace(location_area_filter, '^\\[|\\]$', ''), '\\},\\{')
                                       ) exploded AS pos, val
             ) t1
         group by 1,2,3
     ),comprehensive_filter AS (
    select
        log_id,
        hotel_seq,
        device_id,
        collect_list(
                map(
                        'filterType', get_json_object(comprehensive_filter_array, '$.filterType'),
                        'params', get_json_object(comprehensive_filter_array, '$.params'),
                        'reqParams', get_json_object(comprehensive_filter_array, '$.reqParams')
                )
        ) as comprehensive_filter_array
    from
        (
            SELECT
                log_id,
                hotel_seq,
                device_id,
                get_json_object(comprehensive_filter, concat('$[', pos, ']')) AS comprehensive_filter_array
            FROM (
                     SELECT
                         log_id,
                         hotel_seq,
                         device_id,
                         location_area_filter,
                         comprehensive_filter
                     from
                         default.dw_ihotel_app_search_rank_list_di
                     where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
                 ) t
                     LATERAL VIEW posexplode(
                        split(regexp_replace(comprehensive_filter, '^\\[|\\]$', ''), '\\},\\{')
                                  ) exploded AS pos, val
        ) t1
    group by 1,2,3
)

insert overwrite table default.dwd_ihotel_flow_app_searchlist_di partition(dt)
select

    list.device_id,
    list.platform,
    list.app_version,
    list.user_gps_city_name,
    list.fromforlog,
    list.search_hotel_channel,
    list.is_international,
    list.search_city_code,
    list.search_city_name,
    list.checkin_date,
    list.checkout_date,
    regexp_replace(list.query,'\\\\\n|\\\\\r|\\\\\t|\\\\\\\\','') as query,
    list.is_query,
    list.query_type,
    case when nvl(hotel.city_name,'') = list.user_gps_city_name then 1 when nvl(hotel.city_name,'') <> list.user_gps_city_name then 0 else null end is_same_city,
    list.url,
    list.is_filter,
    split(split(url,'&sort=')[1],'&')[0] as sort,
    list.search_request_uid,
    request_uid.search_request_time,
    list.log_id,
    list.log_hour,
    list.log_datetime,
    list.record_start,
    list.hotel_seq,
    nvl(hotel.city_name,''), --城市
    hotel.city_code,
    nvl(hotel.hotel_area,''), --行政区县
    nvl(hotel.hotel_grade,''), --星级
    null as hotel_show_zone,
    array() as hotel_show_labels,
    display_price as hotel_show_price,
    hotel_score as hotel_show_score,
    comment_nums as hotel_show_comments_num,
    null as hotel_show_type,
    list.medal,
    list.hotel_status,
    case when show2.qtrace_id is not null then 1 else 0 end as is_display,
    list.service_special_type,
    list.hotel_screen_rank,
    list.rank,
    list.nearby_poi_gps,
    list.hotel_poi_distance,
    list.user_hotel_distance,
    list.is_ad,
    case when cilck.qtrace_id is not null then 1 else 0 end as is_click,
    show.device_id qav_device_id,
    show.orig_device_id qav_orig_device_id,
    detail.log_id detail_log_id,
    detail.device_id detail_device_id,
    case when booking.log_id is not null then 1 else 0 end as is_book,
    booking.log_id booking_log_id,
    booking.device_id booking_device_id,
    cast(null as int) is_booking_refresh,
    case when order.log_id is not null then 1 else 0 end as is_submit_order,
    order.log_id order_log_id,
    order.device_id order_device_id,
    order.order_no order_order_no,
    case when order_info.order_no is not null then 1 else 0 end as is_order,
    order_info.order_no order_info_order_no,
    order_info.room_night,
    order_info.device_id order_info_device_id,
    order_info.gmv, --gmv
    order_info.init_commission,
    order_info.profit, --返后佣金
    order_info.pay_type, --支付类型
    null as rate, --费率
    order_info.final_payamount_price, --用户实际支付金额(最终支付金额)
    order_info.init_room_fee, --卖价
    order_info.real_price, --底价
    list.is_recommend,
    list.request_type,
    list.search_type,
    list.recall_type,
    case when t in('h_hlist','fca_h_hlist','h_hhotdog_hSearchList','fca_h_hhotdog_hSearchList','h_hhotdog_hMaplist') and channel_id=1 and search_hotel_channel != 'HOURLY_ROOM' and country_type=1 then 1 else 0 end as is_hotel_channel,
    -- if(t in ('h_hlist','fca_h_hlist','h_hhotdog_hSearchList','fca_h_hhotdog_hSearchList','h_hhotdog_hMaplist') and channel_id=1 and search_hotel_channel<>'HOURLY_ROOM' and country_type=1, 1, 0) as is_hotel_channel,
    list.t,
    list.qtrace_id,
    list.orig_device_id,
    list.channel_id,
    list.country_type,
    list.bizVersion as biz_version,
    split(list.cqp,'#')[1] as cqp,
    list.suggestType as suggest_type,
    list.qFrom as qfrom,
    case when t in ('h_hlist','fca_h_hlist','h_hhotdog_hSearchList','fca_h_hhotdog_hSearchList','h_hhotdog_hMaplist') and search_type in (16,17) then 1 else 0 end as is_largest_search,
    -- if(t in ('h_hlist','fca_h_hlist','h_hhotdog_hSearchList','fca_h_hhotdog_hSearchList','h_hhotdog_hMaplist') and search_type in (16,17), 1, 0) as is_largest_search,
    list.biztype,
    list.is_spider,
    list.allotted_id as gid,
    list.app_id as pid,
    list.app_version as vid,
    list.user_id,
    list.user_name,
    list.province_name,
    list.country_name,
    list.query_parse,
    list.plan_id,
    list.model_sort,
    list.origin_sort,
    list.rerank_sort,
    case when list.recall_type='poi' then get_json_object(pois[0],'$.name') else null end as poi_name,
    case when list.recall_type='poi' then get_json_object(pois[0],'$.type') else null end as poi_type,
    case when list.recall_type='poi' then get_json_object(pois[0],'$.id') else null end as poi_id,
    list.total_hotels,
    list.query_sort,
    map('minprice',min_price,
        'maxprice',max_price
    ) as query_price,
    list.query_hotel_grade,
    list.location_area_filter,
    list.comprehensive_filter,
    list.scene_name,
    baseinfo_city.city_code as user_gps_city_code,
    hotel.hotel_zone_name as hotel_zone_name,
    null as parent_plan_id,
    case when u1.order_date<to_date(list.log_datetime) then 0 else 1 end as is_validord_new_uid, --1新客0老客有效单新老客设备号
    case when u2.orig_device_id is not null then 1 else 0 end as is_validord_new_cuid,--1新客0老客,原始设备号有效单新老客
    case when u3.first_order_date<to_date(list.log_datetime) then 0 else 1 end as is_validord_new_username, --1新客0老客,注册账号有效单新老客
    list.support_ratio,
    case
        when recall_type is NULL then NULL
        when search_type(recall_type)=1 then 'label'
        when size(split(recall_type,',')) <= 1  and recall_type like '%bizZone%' then 'bizZone'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%brand%' then 'brand'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%group%' then 'group'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%poi%' then 'poi'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%genericPoi%' then 'genericPoi'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%hotelName%' then 'hotelName'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%dangci%' then 'dangci'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%subway%' then 'subway'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%fangxing%' then 'fangxing'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%city%' then 'city'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%other%' then 'other'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%subjectRoom%' then 'subjectRoom'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%ctripScenicZone%' then 'ctripScenicZone'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%centerPoint%' then 'centerPoint'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%scenicZone%' then 'scenicZone'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%hotActivity%' then 'hotActivity'
        when size(split(recall_type,',')) <= 1  and  recall_type like '%hotActivityNonLocation%' then 'hotActivityNonLocation'
        else 'composition' end as intention,
    list.real_business,
    list.lr
        ,recall_type_recommend
        ,list.compliance_rate
        ,display_price
        ,hotel_score
        ,comment_nums

    --todo: add columns
        ,is_lose
        ,cpayprice
        ,qpayprice
        ,is_partavaliable_price
        ,is_lose_new
        ,ext_map

        ,list.sort_price
        ,list.render_price

        ,pos as exposure_rank

        ,null
        ,null

        ,location_area_filter_array
        ,comprehensive_filter_array

    --,from_json(
    --    list.location_area_filter,
    --    'array<struct<filterType:string,params:string,reqParams:array<struct<param:string,suggestType:string,secLevelFilter:string,secondShowSelected:boolean,title:string,jsonExtra:string>>>>'
    --)
    --,from_json(
    --    list.comprehensive_filter,
    --    'array<struct<filterType:string,params:string,reqParams:array<struct<param:string,suggestType:string,secLevelFilter:string,secondShowSelected:boolean,title:string,jsonExtra:string>>>>'
    --)


        ,map(
            'physical_room_id', get_json_object(display.extendinfomap, '$.qPhysicalRoomId'),
            'physical_room_status', '1',
            'q_trace', list.qtrace_id,
            'device_id', list.device_id
         ) as physical_room_map

        ,if(hotdog.logExtMap = '[{uSelect:true}]',1,0) search_linkage_filter -- 是否搜筛联动 1 是 0 否
        ,hotdog.adultsNum adults_Num
        ,hotdog.childrenAges children_Ages

        ,if(hotdog.childrenAges is null,0,  SIZE(
        FROM_JSON(
                get_json_object(substr(guestInfos, 3, length(guestInfos) - 4), '$.GuestInfo.childrenAges'),
                'array<int>'
        )
                                            )) children_count

        ,list.dt as dt
from tmp_search_list list
         left join --酒店基础信息
    (select hotel_seq,hotel_name,city_code,city_name,hotel_grade,province_name,hotel_trading_area hotel_zone_name,hotel_area from dim_hotel_info_intl_v3 where dt='${zdt.addDay(-1).format("yyyyMMdd")}') hotel
                   on list.hotel_seq=hotel.hotel_seq
         left join
     ( -- detail
         SELECT
             log_id,
             device_id,
             get_path_node(path,'search').traceid s_id,
             regexp_extract(params,'&ids=([^&]+)',1) AS hotel_seq,
             dt
         FROM dw_user_path_di_v3

         where dt = ${zdt.addDay(-1).format("yyyyMMdd")}
           and process_stage='detail'
           and get_path_node(path,'search').traceid is not null
           and regexp_extract(params,'&ids=([^&]+)',1) is not null
         group by 1,2,3,4,5
     ) detail
     on lower(list.log_id)=lower(detail.s_id) and list.hotel_seq=detail.hotel_seq
         and lower(list.device_id)=lower(detail.device_id)
         left join
     ( --booking
         SELECT
             log_id,
             device_id,
             get_path_node(path,'detail').traceid d_id,
             regexp_extract(params,'&ids=([^&]+)',1) AS hotel_seq,
             dt
         FROM dw_user_path_di_v3

         where dt = ${zdt.addDay(-1).format("yyyyMMdd")}
           and process_stage='booking'
           and get_path_node(path,'detail').traceid is not null
         group by 1,2,3,4,5
     ) booking
     on lower(detail.log_id)=lower(booking.d_id)
         and lower(detail.device_id)=lower(booking.device_id)
         left join
     ( --order_submit
         select
             log_id,
             device_id,
             b_id,
             hotel_seq,
             order_no,
             dt
         from(
                 select
                     log_id,
                     device_id,
                     get_path_node(path,'booking').traceid b_id,
                     regexp_extract(params,'&hotelSeq=([^&]*)&',1) AS hotel_seq,
                     regexp_extract(params,'&orderNo=([^&]*)&',1) AS order_no,
                     row_number() over(partition by get_path_node(path,'booking').traceid order by logtime desc) rn,
                     dt
                 FROM dw_user_path_di_v3
                 where dt = ${zdt.addDay(-1).format("yyyyMMdd")}
                   and process_stage='order'
                   and get_path_node(path,'booking').traceid is not null
             )aa where aa.rn=1
     ) order

on lower(booking.log_id)=lower(order.b_id)
    and lower(booking.device_id)=lower(order.device_id)
    and list.dt = order.dt
    left join (
    select
    dt,
    order_date,
    device_id,
    order_no,
    room_night,
    init_gmv gmv, -- 国际口径
    nvl(init_commission_after,0)
    + nvl(case when batch_series in ('3night_ZK_ad8c83','MacaoDisco_ZK_5e27de','2night_ZK_952825','hanguo55_MJ_e54bf4') then coupon_substract end,0)
    as profit, -- 国际口径
    final_payamount_price,
    init_commission,
    pay_type,
    init_room_fee, --卖价
    init_room_fee - init_commission real_price --底价
    from
    default.mdw_order_v3_international t1
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
    and order_date = '${zdt.addDay(-1).format("yyyy-MM-dd")}'
    and (province_name in ('台湾','澳门','香港') or country_name !='中国')
    and terminal_channel_type in ('www','app','touch') and is_valid='1'

    ) order_info
    on order.order_no=order_info.order_no

    -- left join (

--    select
    --       dt,
--        traceid,
--        hotel_seq,
--        device_id,
--        orig_device_id
--    from( --list页酒店卡片点击
--        select
--            dt,
--            get_json_object(value,'$.ext.params.traceId') as traceid,
--            get_json_object(value,'$.ext.params.ids') as hotel_seq,
--            device_id,
    --           orig_device_id,
--            user_name
--        from dw_qav_hotel_track_info_di
--         $WHERE
--        and key in('ihotel/GList/GListCard/click/hotelCell')
--        and get_json_object(value,'$.ext.params.traceId') !=''
--        and get_json_object(value,'$.ext.params.ids') !=''
--    )aa
--    group by 1,2,3,4,5
-- ) qav
-- on list.qtrace_id=qav.traceid and list.hotel_seq=qav.hotel_seq and list.dt = qav.dt
-- left join htemp.dw_hotel_list2client_2_$DATE listToClient
-- on list.dt=listToclient.dt and list.qtrace_id=listToClient.qtrace_id and list.hotel_seq=listToClient.hotel_seq
-- left join
-- (
    --酒店佣金费率
--  select
--    hotel_seq,
--    rate
--  from (
--      select
--        hotel_seq,
--        effect_date,
--        create_time,
--        update_time,
--        rate,
--        row_number() over(partition by hotel_seq order by update_time desc) rn
--      from ods_h_ims_manager_cps_effect_info
--      where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
--        and effect_date = '$FORMAT_DATE'
--        and effect_status=3
--        and rate != 0
--        and 1=2 -- 先剔除
--    ) t
--    where rn = 1
--) hotel_rate
--on list.hotel_seq = hotel_rate.hotel_seq
-- inner join(
--  select
--    log_id,
--    user_gps_city_name,
--    if(length(location_area_filter_log) > 0 or length(comprehensive_filter_log) > 0 or min_price>0 or max_price>0 or size(query_hotel_grade)>0,1,0) as is_filter,
--    query_sort,
--    if(min_price is null and max_price is null,null,
--    map('minprice',min_price,
--        'maxprice',max_price
--    )) as query_price,
--    query_hotel_grade,
--    location_area_filter_log as location_area_filter,
--    comprehensive_filter_log as comprehensive_filter,
--    action_entrance_map['fromforlog'] as fromforlog,
--    bizVersion,
--    cqp,
--    suggestType,
--    qFrom
--  from
--     htemp.dw_user_app_search_di_$DATE
-- ) search on search.log_id = list.log_id
    left join (
    select
    search_request_uid,
    min(log_datetime) as search_request_time
    from tmp_search_list
    where search_request_uid is not null
    group by 1
    ) request_uid
    on list.search_request_uid=request_uid.search_request_uid
    left join (
    select
    city_name,
    city_code
    from dim_hotel_info_intl_v3
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
    and city_name is not null
    group by 1,2
    ) baseinfo_city
    on list.user_gps_city_name = baseinfo_city.city_name
    -- left join
-- (
--    select
--        plan_id,
--        parent_plan_id
--    from ods_crm_data_support_plan
--    where dt = '$DATE' and 1=2  -- 先剔除
-- )plan
-- on coalesce(list.plan_id, concat(rand(),'hive'))  = plan.plan_id
    left join (
    select
    lower(device_id)device_id,
    min(order_date) order_date
    from mdw_active_user_first_date
    where dt = '${zdt.addDay(-2).format("yyyyMMdd")}' and 1=2  -- 先剔除
    and order_date <= '${zdt.addDay(-2).format("yyyy-MM-dd")}'
    group by 1
    )u1 on lower(list.device_id) = u1.device_id
    left join (
    select
    lower(uid)orig_device_id
    from pf_risk_control.ads_flow_risk_control_new_guest_request_data_di
    where substring(dt,0,10) = '$FORMAT_DATE' and 1=2  -- 先剔除
    and new_user='true'
    and nvl(uid,'')!=''
    and order_no is not null
    and app_code = 'h_order_horus_intl'
    group by 1
    )u2 on lower(list.orig_device_id)= u2.orig_device_id
    left join (

    select
    user_id u_user_id ,order_date first_order_date
    from
    (
    select
    user_id ,order_no ,order_date ,order_time
    ,ROW_NUMBER() over (partition by user_id order by order_time) as rk
    from
    mdw_order_v3_international
    where dt='${zdt.addDay(-1).format("yyyyMMdd")}'
    and (province_name in ('台湾','澳门','香港') or country_name !='中国')
    and terminal_channel_type in ('www','app','touch') and is_valid='1'
    and order_status not in ('CANCELLED','REJECTED')
    and user_id is not null and user_id <> 0
    )u
    where rk=1
    )u3 on lower(list.user_id) = u3.u_user_id

    LEFT JOIN ihotel_show_dispaly_temp show
    ON list.qtrace_id=show.qtrace_id and list.hotel_seq=show.hotel_seq

    left join (
    select
    get_json_object(value, '$.ext.traceId') qtrace_id,
    get_json_object(value, '$.ext.ids') hotel_seq,
    get_json_object(value, '$.ext.pos') pos
    from
    default.dw_qav_ihotel_track_info_di
    where
    dt='${zdt.addDay(-1).format("yyyyMMdd")}'
    and key in ('ihotel/list/listPage/show/hotelCellShow')

    ) show2
    on list.qtrace_id=show2.qtrace_id and list.hotel_seq=show2.hotel_seq

    LEFT JOIN ihotel_cilck_temp cilck
    ON list.qtrace_id=cilck.qtrace_id and list.hotel_seq=cilck.hotel_seq

    left join location_area_filter tb_location_area
    on lower(list.log_id)=lower(tb_location_area.log_id)
    and lower(list.device_id)=lower(tb_location_area.device_id)

    left join comprehensive_filter tb_comprehensive
    on lower(list.log_id)=lower(tb_comprehensive.log_id)
    and lower(list.device_id)=lower(tb_comprehensive.device_id)

    left join
    (select qtrace_id display_qtrace_id,extendinfomap
    from ihotel_default.dw_hotel_price_display
    where dt = '${zdt.addDay(-1).format("yyyyMMdd")}'
    )
    display
    on list.qtrace_id = display.display_qtrace_id

    left join
    (
    select
    trace_id log_id,
    qtrace_id hotdog_qtrace_id,
    param,
    logExtMap,
    guestInfos,
    get_json_object(
    substr(guestinfos, 3, length(guestinfos) - 4),  -- 去除外层 [{{ 和 }}]
    '$.GuestInfo.adultsNum'
    ) AS adultsNum,
    -- 提取 childrenAges
    get_json_object(
    substr(guestinfos, 3, length(guestinfos) - 4),
    '$.GuestInfo.childrenAges'
    ) AS childrenAges
    from
    ihotel_default.ods_hotel_hotdog_log_di
    LATERAL VIEW get_params_tuple(param, 'QUERY:logExtMap', 'QUERY:guestInfos') p as logExtMap, guestInfos
    where
    dt =  '${zdt.addDay(-1).format("yyyyMMdd")}'
    ) hotdog
    on list.qtrace_id = hotdog.hotdog_qtrace_id




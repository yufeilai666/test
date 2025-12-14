import json

def transform_json_structure(input_file, output_file):
    # 读取原始JSON文件
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 转换结构：将每个值包装到数组中
    transformed_data = {}
    for key, value in data.items():
        transformed_data[key] = [value]
    
    # 写入新的JSON文件
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(transformed_data, f, ensure_ascii=False, indent=2)
    
    print(f"转换完成！结果已保存到 {output_file}")

# 使用示例
if __name__ == "__main__":
    input_file = "epg_title_info.json"  # 输入文件名
    output_file = "epg_title_info_transformed.json"  # 输出文件名
    
    transform_json_structure(input_file, output_file)
import os
import json
from dotenv import load_dotenv, find_dotenv
from flask import Flask, request, render_template, jsonify
import openai

# Load environment variables from .env file
_ = load_dotenv(find_dotenv())

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')

app = Flask(__name__)

# Load checklist prompts from JSON file
with open('checklist_prompts.json', 'r') as file:
    checklist_prompts = json.load(file)

# Load system, subsystem, component, and spec data from JSON file
with open('data.json', 'r') as file:
    data = json.load(file)

def find_related_entities(requirement):
    related_system = None
    related_subsystem = None
    related_component = None
    related_specs = []

    for system, keywords in data["systems"].items():
        if any(keyword.lower() in requirement.lower() for keyword in keywords):
            related_system = system
            for subsystem in data["systems_to_subsystems"].get(system, []):
                related_subsystem = subsystem
                for component in data["subsystems_to_components"].get(subsystem, []):
                    related_component = component

    if related_component:
        for component, keywords in data["components"].items():
            if any(keyword.lower() in requirement.lower() for keyword in keywords):
                related_specs.extend([(spec, data["specs"][spec]["description"]) for spec in keywords])

    return related_system, related_subsystem, related_component, related_specs

def review_and_improve_requirement(requirement, checklist_item, model="gpt-3.5-turbo", temperature=0):
    checklist = checklist_prompts[checklist_item]
    overall_instructions = checklist_prompts["Overall Instructions"]["Instructions"]
    prompt = (
        f"{overall_instructions}\n\nRequirement: {checklist['Requirement']}\n"
        f"Instructions: {checklist['Instructions to assess the requirement']}\n"
        f"Inference if condition met: {checklist['Inference: if condition met print text in']}\n"
        f"Inference if condition not met: {checklist['Inference: If condition not met print text in']}\n"
        f"Recommendation if condition not met: {checklist.get('Recommendation', 'N/A')}\n\n"
        f"Current Requirement: {requirement}\n\n"
        f"Please review the requirement based on the criteria above. If the requirement does not meet the criteria, provide an improved version of the requirement based on the recommendation."
    )
    prompt = prompt.format(requirement=requirement)
    
    messages = [
        {"role": "system", "content": "Review system engineering requirements. Print if the example requirement met the criteria, then mention if it PASSED or NOT PASSED, provide the inference, recommendation if not passed, and a corrected version of the requirement."},
        {"role": "user", "content": prompt}
    ]
    
    response = openai.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    
    return response.choices[0].message.content

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    requirement = request.form['requirement']
    processing_updates = []
    recommendations = []
    final_corrected_requirement = requirement

    for checklist_item in checklist_prompts:
        if checklist_item == "Overall Instructions":
            continue  # Skip the overall instructions

        comment = review_and_improve_requirement(requirement, checklist_item)
        
        if "NOT PASSED" in comment:
            recommendation = checklist_prompts[checklist_item].get("Recommendation", "No recommendation available.")
            recommendations.append(f"Checklist Item: {checklist_item}\nRecommendation: {recommendation}\n")
            if "Corrected Requirement:" in comment:
                improved_requirement = comment.split("Corrected Requirement:")[-1].strip()
                final_corrected_requirement = improved_requirement  # Update the final corrected requirement
                processing_updates.append(f"Processing checklist item: {checklist_item}\nCorrected Requirement: {final_corrected_requirement}\n\n")
    
    related_system, related_subsystem, related_component, related_specs = find_related_entities(final_corrected_requirement)

    related_entities_output = ""
    if related_component:
        related_entities_output = f"Related Component: {related_component}\nRelated Specs:\n" + "\n".join([f"• {spec}: {description}" for spec, description in related_specs])
    elif related_subsystem:
        related_entities_output = f"Related Subsystem: {related_subsystem}\nRelated Specs:\n" + "\n".join([f"• {spec}: {description}" for spec, description in related_specs])
    elif related_system:
        related_entities_output = f"Related System: {related_system}\nRelated Specs:\n" + "\n".join([f"• {spec}: {description}" for spec, description in related_specs])

    final_output = "\nRecommendations for NOT PASSED Items:\n" + "\n".join(recommendations)

    return jsonify(
        processing_updates=processing_updates, 
        final_output=final_output, 
        final_corrected_requirement=final_corrected_requirement,
        related_entities_output=related_entities_output
    )

if __name__ == '__main__':
    app.run(debug=True)

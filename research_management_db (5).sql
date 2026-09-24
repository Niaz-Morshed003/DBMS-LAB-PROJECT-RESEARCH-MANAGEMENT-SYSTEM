SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

CREATE TABLE `active_projects_view` (
`project_id` int(11)
,`title` varchar(255)
,`status` varchar(50)
);

CREATE TABLE `application` (
  `project_id` int(11) NOT NULL,
  `application_id` int(11) NOT NULL,
  `student_id` int(11) NOT NULL,
  `cover_letter` text DEFAULT NULL,
  `applied_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `status` varchar(50) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `application` (`project_id`, `application_id`, `student_id`, `cover_letter`, `applied_at`, `status`) VALUES
(1, 1, 1, 'Strong interest in network security.', '2026-09-11 14:37:40', 'Pending'),
(1, 2, 2, 'Eager to contribute to anomaly detection.', '2026-09-11 14:37:40', 'Pending'),
(2, 1, 1, 'Familiar with vulnerability scoring.', '2026-09-11 14:37:40', 'Pending'),
(4, 1, 3, 'Experienced in computer vision.', '2026-09-11 14:37:40', 'Pending'),
(4, 2, 5, 'Passionate about deep learning.', '2026-09-11 14:37:40', 'Pending'),
(4, 3, 2, 'Ready to work on image forensics.', '2026-09-11 14:37:40', 'Pending'),
(5, 1, 4, 'Interested in NLP conversational agents.', '2026-09-11 14:37:40', 'Pending'),
(5, 2, 1, 'Background in text processing.', '2026-09-11 14:37:40', 'Pending'),
(6, 1, 3, 'Solid blockchain background.', '2026-09-11 14:37:40', 'Pending'),
(8, 1, 4, 'Skilled in Java and data systems.', '2026-09-11 14:37:40', 'Pending'),
(8, 2, 2, 'Familiar with bug metrics.', '2026-09-11 14:37:40', 'Pending'),
(9, 1, 5, 'Cloud optimization enthusiast.', '2026-09-11 14:37:40', 'Pending'),
(10, 1, 1, 'Edge computing research interest.', '2026-09-11 14:37:40', 'Pending'),
(10, 2, 3, 'C++ systems programmer.', '2026-09-11 14:37:40', 'Pending'),
(11, 1, 6, 'Smart grid researcher.', '2026-09-11 14:37:40', 'Pending'),
(11, 2, 9, 'Power systems background.', '2026-09-11 14:37:40', 'Pending'),
(11, 3, 7, 'MATLAB specialist.', '2026-09-11 14:37:40', 'Pending'),
(13, 1, 8, 'Power electronics coursework done.', '2026-09-11 14:37:40', 'Pending'),
(14, 1, 10, 'FPGA design experience.', '2026-09-11 14:37:40', 'Pending'),
(14, 2, 8, 'Verilog coding skills.', '2026-09-11 14:37:40', 'Pending'),
(15, 1, 11, 'Robotics and ROS background.', '2026-09-11 14:37:40', 'Pending'),
(16, 1, 7, 'Wireless communication focus.', '2026-09-11 14:37:40', 'Pending'),
(16, 2, 9, 'Interested in MIMO systems.', '2026-09-11 14:37:40', 'Pending'),
(18, 1, 12, 'ANSYS thermal simulation expert.', '2026-09-11 14:37:40', 'Pending'),
(19, 1, 11, 'Kinematics project experience.', '2026-09-11 14:37:40', 'Pending'),
(19, 2, 15, 'SolidWorks CAD designer.', '2026-09-11 14:37:40', 'Pending'),
(19, 3, 12, 'Mechatronics enthusiast.', '2026-09-11 14:37:40', 'Pending'),
(20, 1, 15, 'Active suspension modeling interest.', '2026-09-11 14:37:40', 'Pending'),
(20, 2, 11, 'Control systems background.', '2026-09-11 14:37:40', 'Pending'),
(22, 1, 13, 'SolidWorks and manufacturing focus.', '2026-09-11 14:37:40', 'Pending'),
(23, 1, 16, 'Structural analysis skills.', '2026-09-11 14:37:40', 'Pending'),
(23, 2, 17, 'STAAD.Pro certified.', '2026-09-11 14:37:40', 'Pending'),
(24, 1, 18, 'Revit and structural design.', '2026-09-11 14:37:40', 'Pending'),
(26, 1, 20, 'GIS mapping specialist.', '2026-09-11 14:37:40', 'Pending'),
(26, 2, 16, 'Data analysis background.', '2026-09-11 14:37:40', 'Pending'),
(27, 1, 19, 'Environmental engineering major.', '2026-09-11 14:37:40', 'Pending'),
(28, 1, 18, 'BIM workflow knowledge.', '2026-09-11 14:37:40', 'Pending'),
(28, 2, 16, 'Python safety script developer.', '2026-09-11 14:37:40', 'Pending'),
(28, 3, 20, 'Geospatial site mapping.', '2026-09-11 14:37:40', 'Pending'),
(29, 1, 21, 'Signal processing research interest.', '2026-09-11 14:37:40', 'Pending'),
(29, 2, 25, 'Neural engineering background.', '2026-09-11 14:37:40', 'Pending'),
(30, 1, 21, 'Python spike sorting scripts.', '2026-09-11 14:37:40', 'Pending'),
(32, 1, 22, 'Biomaterials coursework.', '2026-09-11 14:37:40', 'Pending'),
(32, 2, 23, 'Medical imaging experience.', '2026-09-11 14:37:40', 'Pending'),
(33, 1, 24, 'Bioinformatics algorithms in C++.', '2026-09-11 14:37:40', 'Pending'),
(34, 1, 25, 'Biosensor lab assistant.', '2026-09-11 14:37:40', 'Pending'),
(34, 2, 22, 'LabVIEW programming skill.', '2026-09-11 14:37:40', 'Pending'),
(35, 1, 26, 'Nanotechnology interest.', '2026-09-11 14:37:40', 'Pending'),
(37, 1, 27, 'Polymer science research assistant.', '2026-09-11 14:37:40', 'Pending'),
(37, 2, 28, 'Materials lab experience.', '2026-09-11 14:37:40', 'Pending'),
(38, 1, 29, 'Semiconductor crystal growth.', '2026-09-11 14:37:40', 'Pending'),
(39, 1, 30, 'Composite materials background.', '2026-09-11 14:37:40', 'Pending'),
(39, 2, 26, 'Materials characterization skill.', '2026-09-11 14:37:40', 'Pending'),
(40, 1, 21, 'Cardiovascular flow simulation interest.', '2026-09-11 14:37:40', 'Pending'),
(40, 2, 22, 'Fluid modeling background.', '2026-09-11 14:37:40', 'Pending');

CREATE TABLE `faculty` (
  `faculty_id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `designation` varchar(100) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `office_hours` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `faculty` (`faculty_id`, `name`, `designation`, `department`, `office_hours`) VALUES
(31, 'Dr. Faculty CSE 1', 'Professor', 'CSE', 'Sun-Tue 10:00 AM'),
(32, 'Dr. Faculty CSE 2', 'Associate Professor', 'CSE', 'Mon-Wed 11:00 AM'),
(33, 'Dr. Faculty CSE 3', 'Assistant Professor', 'CSE', 'Sun-Thu 02:00 PM'),
(34, 'Mr. Faculty CSE 4', 'Lecturer', 'CSE', 'Sat-Mon 09:00 AM'),
(35, 'Mr. Faculty CSE 5', 'Senior Lecturer', 'CSE', 'Tue-Wed 01:00 PM'),
(36, 'Dr. Faculty EEE 1', 'Professor', 'EEE', 'Sun-Wed 10:00 AM'),
(37, 'Dr. Faculty EEE 2', 'Associate Professor', 'EEE', 'Mon-Thu 12:00 PM'),
(38, 'Dr. Faculty EEE 3', 'Assistant Professor', 'EEE', 'Sun-Tue 03:00 PM'),
(39, 'Mr. Faculty EEE 4', 'Lecturer', 'EEE', 'Sat-Wed 10:00 AM'),
(40, 'Mr. Faculty EEE 5', 'Senior Lecturer', 'EEE', 'Sun-Thu 11:00 AM'),
(41, 'Dr. Faculty ME 1', 'Professor', 'Mechanical Engineering', 'Mon-Wed 02:00 PM'),
(42, 'Dr. Faculty ME 2', 'Associate Professor', 'Mechanical Engineering', 'Sun-Thu 10:00 AM'),
(43, 'Dr. Faculty ME 3', 'Assistant Professor', 'Mechanical Engineering', 'Sat-Mon 11:00 AM'),
(44, 'Mr. Faculty ME 4', 'Lecturer', 'Mechanical Engineering', 'Sun-Tue 01:00 PM'),
(45, 'Mr. Faculty ME 5', 'Senior Lecturer', 'Mechanical Engineering', 'Tue-Wed 03:00 PM'),
(46, 'Dr. Faculty CE 1', 'Professor', 'Civil Engineering', 'Sun-Wed 09:00 AM'),
(47, 'Dr. Faculty CE 2', 'Associate Professor', 'Civil Engineering', 'Mon-Thu 02:00 PM'),
(48, 'Dr. Faculty CE 3', 'Assistant Professor', 'Civil Engineering', 'Sat-Mon 10:00 AM'),
(49, 'Mr. Faculty CE 4', 'Lecturer', 'Civil Engineering', 'Sun-Tue 11:00 AM'),
(50, 'Mr. Faculty CE 5', 'Senior Lecturer', 'Civil Engineering', 'Tue-Wed 02:00 PM'),
(51, 'Dr. Faculty BME 1', 'Professor', 'Biomedical Engineering', 'Sun-Thu 10:00 AM'),
(52, 'Dr. Faculty BME 2', 'Associate Professor', 'Biomedical Engineering', 'Mon-Wed 11:00 AM'),
(53, 'Dr. Faculty BME 3', 'Assistant Professor', 'Biomedical Engineering', 'Sat-Tue 01:00 PM'),
(54, 'Mr. Faculty BME 4', 'Lecturer', 'Biomedical Engineering', 'Sun-Wed 03:00 PM'),
(55, 'Mr. Faculty BME 5', 'Senior Lecturer', 'Biomedical Engineering', 'Mon-Thu 09:00 AM'),
(56, 'Dr. Faculty MSE 1', 'Professor', 'Materials Science', 'Sun-Tue 11:00 AM'),
(57, 'Dr. Faculty MSE 2', 'Associate Professor', 'Materials Science', 'Mon-Wed 02:00 PM'),
(58, 'Dr. Faculty MSE 3', 'Assistant Professor', 'Materials Science', 'Sat-Thu 10:00 AM'),
(59, 'Mr. Faculty MSE 4', 'Lecturer', 'Materials Science', 'Sun-Wed 01:00 PM'),
(60, 'Mr. Faculty MSE 5', 'Senior Lecturer', 'Materials Science', 'Tue-Thu 03:00 PM');

CREATE TABLE `faculty_research_areas` (
  `faculty_id` int(11) NOT NULL,
  `research_area` varchar(150) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `faculty_research_areas` (`faculty_id`, `research_area`) VALUES
(31, 'Machine Learning'),
(31, 'Network Security'),
(32, 'Artificial Intelligence'),
(32, 'Data Science'),
(32, 'NLP'),
(33, 'Blockchain'),
(33, 'Cybersecurity'),
(34, 'Software Engineering'),
(34, 'Web Tech'),
(35, 'Cloud Computing'),
(35, 'Distributed Systems'),
(35, 'Edge Computing'),
(36, 'Renewable Energy'),
(36, 'Smart Grid'),
(37, 'Control Systems'),
(37, 'Power Electronics'),
(38, 'Nanotechnology'),
(38, 'VLSI Design'),
(39, 'Automation'),
(39, 'Robotics'),
(40, '5G Networks'),
(40, 'IoT'),
(40, 'Wireless Communication'),
(41, 'Fluid Mechanics'),
(41, 'Thermal Engineering'),
(42, 'Mechatronics'),
(42, 'Robotics'),
(43, 'Automotive Systems'),
(43, 'Dynamics'),
(44, 'Energy Systems'),
(44, 'HVAC'),
(45, '3D Printing'),
(45, 'CAD/CAM'),
(45, 'Manufacturing'),
(46, 'Earthquake Engineering'),
(46, 'Structural Engineering'),
(47, 'Geotechnical Engineering'),
(47, 'Soil Mechanics'),
(48, 'Highway Design'),
(48, 'Transportation Engineering'),
(49, 'Environmental Engineering'),
(49, 'Water Resources'),
(50, 'BIM'),
(50, 'Construction Management'),
(50, 'Project Planning'),
(51, 'Biomedical Signal Processing'),
(51, 'Neural Engineering'),
(52, 'Biomaterials'),
(52, 'Medical Imaging'),
(53, 'Biomechanics'),
(53, 'Tissue Engineering'),
(54, 'Bioinformatics'),
(54, 'Genomics'),
(55, 'Biosensors'),
(55, 'Microfluidics'),
(55, 'Nanomedicine'),
(56, 'Advanced Materials'),
(56, 'Nanomaterials'),
(57, 'Corrosion Science'),
(57, 'Metallurgy'),
(58, 'Composite Materials'),
(58, 'Polymer Chemistry'),
(59, 'Electronic Materials'),
(59, 'Semiconductors'),
(60, 'Ceramics'),
(60, 'Surface Science');

CREATE TABLE `research_project` (
  `project_id` int(11) NOT NULL,
  `title` varchar(255) NOT NULL,
  `description` text DEFAULT NULL,
  `required_skill` text DEFAULT NULL,
  `status` varchar(50) DEFAULT NULL,
  `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
  `applicant_count` int(11) DEFAULT 0,
  `faculty_id` int(11) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `research_project` (`project_id`, `title`, `description`, `required_skill`, `status`, `created_at`, `applicant_count`, `faculty_id`) VALUES
(1, 'ML in Network Security', 'Detecting anomalies in high-speed networks.', 'Python, ML', 'Active', '2026-09-11 14:37:40', 2, 31),
(2, 'Zero-Day Vulnerability Analysis', 'Predicting software vulnerabilities.', 'Python, Security', 'Active', '2026-09-11 14:37:40', 1, 31),
(3, 'AI Threat Intelligence', 'Threat detection with deep learning.', 'Python, PyTorch', 'Active', '2026-09-11 14:37:40', 0, 31),
(4, 'Deep Fake Detection', 'Identifying manipulated media files.', 'Python, Deep Learning', 'Active', '2026-09-11 14:37:40', 3, 32),
(5, 'Conversational Clinical Agents', 'NLP bots for preliminary triage.', 'Python, NLP', 'Active', '2026-09-11 14:37:40', 2, 32),
(6, 'Smart Contract Auditing', 'Automated security checks for Solidity.', 'Solidity, Security', 'Active', '2026-09-11 14:37:40', 1, 33),
(7, 'Decentralized Identity Frameworks', 'Self-sovereign identity design.', 'Blockchain, Cryptography', 'Active', '2026-09-11 14:37:40', 0, 33),
(8, 'Agile Metrics Predictor', 'Predicting software release bugs.', 'Java, Statistics', 'Active', '2026-09-11 14:37:40', 2, 34),
(9, 'Serverless Cost Optimization', 'Cloud function efficiency modeling.', 'Cloud, Python', 'Active', '2026-09-11 14:37:40', 1, 35),
(10, 'Edge Computing Offloading', 'Task scheduling in fog networks.', 'C++, Networking', 'Active', '2026-09-11 14:37:40', 2, 35),
(11, 'Smart Grid Frequency Control', 'Renewable integration stability.', 'MATLAB, Control Systems', 'Active', '2026-09-11 14:37:40', 3, 36),
(12, 'Solar Farm Fault Diagnostics', 'IoT-based panel monitoring.', 'IoT, Python', 'Active', '2026-09-11 14:37:40', 0, 36),
(13, 'Electric Vehicle Powertrain', 'Inverter efficiency optimization.', 'Power Electronics', 'Active', '2026-09-11 14:37:40', 1, 37),
(14, 'Low-Power VLSI Architectures', 'Energy-efficient chip design.', 'Verilog, FPGA', 'Active', '2026-09-11 14:37:40', 2, 38),
(15, 'Autonomous Delivery Drones', 'Path planning in urban canyons.', 'C++, ROS', 'Active', '2026-09-11 14:37:40', 1, 39),
(16, '5G Massive MIMO Optimization', 'Beamforming algorithm design.', 'MATLAB, Wireless', 'Active', '2026-09-11 14:37:40', 2, 40),
(17, 'IoT Industrial Sensor Networks', 'Reliable industrial automation.', 'IoT, C++', 'Active', '2026-09-11 14:37:40', 0, 40),
(18, 'Microfluidic Heat Exchangers', 'Cooling high-power electronics.', 'ANSYS, Thermal', 'Active', '2026-09-11 14:37:40', 1, 41),
(19, 'Exoskeleton Joint Kinematics', 'Assistive tech for mobility.', 'SolidWorks, Kinematics', 'Active', '2026-09-11 14:37:40', 3, 42),
(20, 'Autonomous Vehicle Suspension', 'Active damping controllers.', 'MATLAB, Control', 'Active', '2026-09-11 14:37:40', 2, 43),
(21, 'Building Energy Simulation', 'HVAC load forecasting.', 'Python, Thermodynamics', 'Active', '2026-09-11 14:37:40', 0, 44),
(22, 'Additive Manufacturing Toolpaths', 'Optimizing 3D printing layers.', 'CAD, CAM', 'Active', '2026-09-11 14:37:40', 1, 45),
(23, 'Seismic Retrofitting of Bridges', 'Ductility analysis under load.', 'STAAD.Pro, Structural', 'Active', '2026-09-11 14:37:40', 2, 46),
(24, 'High-Rise Wind Load Analysis', 'CFD simulation of skyscrapers.', 'ANSYS, Fluid Dynamics', 'Active', '2026-09-11 14:37:40', 1, 46),
(25, 'Liquefaction Hazard Mapping', 'Soil behavior during earthquakes.', 'Geotech, Soil Mechanics', 'Active', '2026-09-11 14:37:40', 0, 47),
(26, 'Smart Traffic Corridor Design', 'Signal timing optimization.', 'GIS Mapping, Traffic', 'Active', '2026-09-11 14:37:40', 2, 48),
(27, 'Urban Wastewater Bioremediation', 'Filtering heavy metals.', 'Environmental, Chemistry', 'Active', '2026-09-11 14:37:40', 1, 49),
(28, 'BIM-based Safety Monitoring', 'Real-time hazard detection on site.', 'Revit, Python', 'Active', '2026-09-11 14:37:40', 3, 50),
(29, 'EEG Signal Classification', 'BCI for motor imagery.', 'Python, Signal Processing', 'Active', '2026-09-11 14:37:40', 2, 51),
(30, 'Neural Spike Sorting', 'Unsupervised clustering of neurons.', 'Python, Neural Networks', 'Active', '2026-09-11 14:37:40', 1, 51),
(31, 'MRI Segmentation with AI', 'Tumor boundary identification.', 'Python, Medical Imaging', 'Active', '2026-09-11 14:37:40', 0, 52),
(32, 'Bone Scaffold Biocompatibility', '3D printed porous implants.', 'Biomaterials, CAD', 'Active', '2026-09-11 14:37:40', 2, 53),
(33, 'Proteomic Sequence Alignment', 'Fast alignment algorithms.', 'C++, Bioinformatics', 'Active', '2026-09-11 14:37:40', 1, 54),
(34, 'Point-of-Care Biosensors', 'Microfluidic pathogen detection.', 'Biosensors, LabVIEW', 'Active', '2026-09-11 14:37:40', 2, 55),
(35, 'Advanced Malware Analysis', 'Reverse engineering unknown binaries.', 'Assembly, C++', 'Active', '2026-09-11 14:37:40', 1, 31),
(36, 'Quantum Key Distribution Simulator', 'Simulating QKD networks.', 'Python, Cryptography', 'Active', '2026-09-11 14:37:40', 2, 32),
(37, 'Smart Microgrid Protection', 'Relay coordination using AI.', 'MATLAB, Power Systems', 'Active', '2026-09-11 14:37:40', 0, 36),
(38, 'Autonomous Mobile Robots', 'SLAM mapping and localization.', 'ROS, C++', 'Active', '2026-09-11 14:37:40', 2, 39),
(39, 'Composite Material Fatigue Life', 'Cyclic loading analysis.', 'Materials Science', 'Active', '2026-09-11 14:37:40', 1, 46),
(40, 'Cardiovascular Flow Simulations', 'Blood flow dynamics in stents.', 'ANSYS, Biomedical', 'Active', '2026-09-11 14:37:40', 2, 51);

CREATE TABLE `student` (
  `student_id` int(11) NOT NULL,
  `name` varchar(255) NOT NULL,
  `cgpa` decimal(3,2) DEFAULT NULL,
  `department` varchar(100) DEFAULT NULL,
  `semester` varchar(50) DEFAULT NULL,
  `github_link` varchar(255) DEFAULT NULL,
  `cv_link` varchar(255) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `student` (`student_id`, `name`, `cgpa`, `department`, `semester`, `github_link`, `cv_link`) VALUES
(1, 'Student CSE 1', 3.85, 'CSE', '8th', 'https://github.com/s1', 'https://cv.com/1'),
(2, 'Student CSE 2', 3.75, 'CSE', '7th', 'https://github.com/s2', 'https://cv.com/2'),
(3, 'Student CSE 3', 3.90, 'CSE', '6th', 'https://github.com/s3', 'https://cv.com/3'),
(4, 'Student CSE 4', 3.65, 'CSE', '5th', 'https://github.com/s4', 'https://cv.com/4'),
(5, 'Student CSE 5', 3.80, 'CSE', '8th', 'https://github.com/s5', 'https://cv.com/5'),
(6, 'Student EEE 1', 3.70, 'EEE', '7th', 'https://github.com/s6', 'https://cv.com/6'),
(7, 'Student EEE 2', 3.82, 'EEE', '8th', 'https://github.com/s7', 'https://cv.com/7'),
(8, 'Student EEE 3', 3.55, 'EEE', '6th', 'https://github.com/s8', 'https://cv.com/8'),
(9, 'Student EEE 4', 3.91, 'EEE', '5th', 'https://github.com/s9', 'https://cv.com/9'),
(10, 'Student EEE 5', 3.60, 'EEE', '8th', 'https://github.com/s10', 'https://cv.com/10'),
(11, 'Student ME 1', 3.72, 'Mechanical Engineering', '6th', 'https://github.com/s11', 'https://cv.com/11'),
(12, 'Student ME 2', 3.88, 'Mechanical Engineering', '7th', 'https://github.com/s12', 'https://cv.com/12'),
(13, 'Student ME 3', 3.45, 'Mechanical Engineering', '5th', 'https://github.com/s13', 'https://cv.com/13'),
(14, 'Student ME 4', 3.79, 'Mechanical Engineering', '8th', 'https://github.com/s14', 'https://cv.com/14'),
(15, 'Student ME 5', 3.68, 'Mechanical Engineering', '6th', 'https://github.com/s15', 'https://cv.com/15'),
(16, 'Student CE 1', 3.81, 'Civil Engineering', '8th', 'https://github.com/s16', 'https://cv.com/16'),
(17, 'Student CE 2', 3.59, 'Civil Engineering', '7th', 'https://github.com/s17', 'https://cv.com/17'),
(18, 'Student CE 3', 3.94, 'Civil Engineering', '6th', 'https://github.com/s18', 'https://cv.com/18'),
(19, 'Student CE 4', 3.67, 'Civil Engineering', '5th', 'https://github.com/s19', 'https://cv.com/19'),
(20, 'Student CE 5', 3.74, 'Civil Engineering', '8th', 'https://github.com/s20', 'https://cv.com/20'),
(21, 'Student BME 1', 3.89, 'Biomedical Engineering', '7th', 'https://github.com/s21', 'https://cv.com/21'),
(22, 'Student BME 2', 3.52, 'Biomedical Engineering', '6th', 'https://github.com/s22', 'https://cv.com/22'),
(23, 'Student BME 3', 3.77, 'Biomedical Engineering', '8th', 'https://github.com/s23', 'https://cv.com/23'),
(24, 'Student BME 4', 3.83, 'Biomedical Engineering', '5th', 'https://github.com/s24', 'https://cv.com/24'),
(25, 'Student BME 5', 3.61, 'Biomedical Engineering', '7th', 'https://github.com/s25', 'https://cv.com/25'),
(26, 'Student MSE 1', 3.92, 'Materials Science', '8th', 'https://github.com/s26', 'https://cv.com/26'),
(27, 'Student MSE 2', 3.66, 'Materials Science', '6th', 'https://github.com/s27', 'https://cv.com/27'),
(28, 'Student MSE 3', 3.73, 'Materials Science', '7th', 'https://github.com/s28', 'https://cv.com/28'),
(29, 'Student MSE 4', 3.80, 'Materials Science', '5th', 'https://github.com/s29', 'https://cv.com/29'),
(30, 'Student MSE 5', 3.58, 'Materials Science', '8th', 'https://github.com/s30', 'https://cv.com/30');

CREATE TABLE `student_skills` (
  `student_id` int(11) NOT NULL,
  `skill` varchar(100) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `student_skills` (`student_id`, `skill`) VALUES
(1, 'Machine Learning'),
(1, 'Networking'),
(1, 'Python'),
(2, 'Data Structures'),
(2, 'Git'),
(2, 'Python'),
(2, 'SQL'),
(3, 'Algorithms'),
(3, 'C++'),
(3, 'Java'),
(4, 'Java'),
(4, 'Spring Boot'),
(4, 'SQL'),
(5, 'Deep Learning'),
(5, 'NLP'),
(5, 'Python'),
(5, 'PyTorch'),
(6, 'Circuit Design'),
(6, 'IoT'),
(6, 'Python'),
(7, 'MATLAB'),
(7, 'Signal Processing'),
(7, 'Simulink'),
(8, 'C++'),
(8, 'Embedded Systems'),
(9, 'Electrical Safety'),
(9, 'Power Systems'),
(9, 'Python'),
(10, 'FPGA'),
(10, 'Verilog'),
(11, 'C++'),
(11, 'CAD'),
(11, 'Robotics'),
(11, 'ROS'),
(12, 'ANSYS'),
(12, 'Thermodynamics'),
(13, 'AutoCAD'),
(13, 'Machine Design'),
(13, 'SolidWorks'),
(14, 'Fluid Dynamics'),
(14, 'Python'),
(15, 'Dynamics'),
(15, 'Kinematics'),
(15, 'MATLAB'),
(16, 'AutoCAD'),
(16, 'Data Analysis'),
(16, 'Python'),
(16, 'Statistics'),
(17, 'STAAD.Pro'),
(17, 'Structural Analysis'),
(18, 'Estimation'),
(18, 'Revit'),
(18, 'Surveying'),
(19, 'Concrete Tech'),
(19, 'Geotech'),
(20, 'ArcGIS'),
(20, 'GIS Mapping'),
(20, 'Python'),
(21, 'Biomedical Sensors'),
(21, 'Python'),
(21, 'Signal Processing'),
(22, 'Biomechanics'),
(22, 'LabVIEW'),
(23, 'Image Processing'),
(23, 'MATLAB'),
(23, 'Medical Imaging'),
(24, 'Bioinformatics'),
(24, 'C++'),
(25, 'Neural Engineering'),
(25, 'Python'),
(25, 'Statistics'),
(26, 'Chemistry'),
(26, 'Materials Characterization'),
(26, 'Nanotech'),
(26, 'Python'),
(27, 'Polymer Science'),
(27, 'SEM Analysis'),
(28, 'Material Testing'),
(28, 'Metallurgy'),
(28, 'XRD'),
(29, 'C++'),
(29, 'Crystal Growth'),
(30, 'Composite Materials'),
(30, 'Nanomaterials'),
(30, 'Python');

CREATE TABLE `student_interests` (
  `student_id` int(11) NOT NULL,
  `research_area` varchar(150) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO `student_interests` (`student_id`, `research_area`) VALUES
(1, 'Machine Learning'),
(1, 'Network Security'),
(2, 'Data Science'),
(2, 'NLP'),
(3, 'Artificial Intelligence'),
(3, 'Cybersecurity'),
(4, 'Software Engineering'),
(4, 'Cloud Computing'),
(5, 'Machine Learning'),
(5, 'NLP'),
(6, 'Renewable Energy'),
(6, 'Smart Grid'),
(7, 'Power Electronics'),
(7, 'Control Systems'),
(8, 'VLSI Design'),
(8, 'Nanotechnology'),
(9, 'Smart Grid'),
(9, 'Power Systems'),
(10, 'IoT'),
(10, 'Wireless Communication'),
(11, 'Robotics'),
(11, 'Mechatronics'),
(12, 'Thermal Engineering'),
(12, 'Fluid Mechanics'),
(13, 'Automotive Systems'),
(13, 'Manufacturing'),
(14, 'Robotics'),
(14, 'Manufacturing'),
(15, 'Control Systems'),
(15, 'Dynamics'),
(16, 'Structural Engineering'),
(16, 'Transportation Engineering'),
(17, 'Geotechnical Engineering'),
(17, 'Structural Engineering'),
(18, 'Transportation Engineering'),
(18, 'Environmental Engineering'),
(19, 'Environmental Engineering'),
(19, 'Water Resources'),
(20, 'Construction Management'),
(20, 'Structural Engineering'),
(21, 'Neural Engineering'),
(21, 'Biomedical Signal Processing'),
(22, 'Biomaterials'),
(22, 'Medical Imaging'),
(23, 'Medical Imaging'),
(23, 'Tissue Engineering'),
(24, 'Genomics'),
(24, 'Bioinformatics'),
(25, 'Biosensors'),
(25, 'Nanomedicine'),
(26, 'Nanomaterials'),
(26, 'Advanced Materials'),
(27, 'Polymer Science'),
(27, 'Nanomaterials'),
(28, 'Metallurgy'),
(28, 'Corrosion Science'),
(29, 'Semiconductors'),
(29, 'Electronic Materials'),
(30, 'Composite Materials'),
(30, 'Nanomaterials');

CREATE TABLE `user` (
  `user_id` int(11) NOT NULL,
  `email` varchar(255) NOT NULL,
  `password` varchar(255) NOT NULL,
  `role` varchar(50) NOT NULL
);

INSERT INTO `user` (`user_id`, `email`, `password`, `role`) VALUES
(1, 'student1@cse.uiu.ac.bd', 'CSE-Std#1', 'Student'),
(2, 'student2@cse.uiu.ac.bd', 'CSE-Std#2', 'Student'),
(3, 'student3@cse.uiu.ac.bd', 'CSE-Std#3', 'Student'),
(4, 'student4@cse.uiu.ac.bd', 'CSE-Std#4', 'Student'),
(5, 'student5@cse.uiu.ac.bd', 'CSE-Std#5', 'Student'),
(6, 'student1@eee.uiu.ac.bd', 'EEE-Std#1', 'Student'),
(7, 'student2@eee.uiu.ac.bd', 'EEE-Std#2', 'Student'),
(8, 'student3@eee.uiu.ac.bd', 'EEE-Std#3', 'Student'),
(9, 'student4@eee.uiu.ac.bd', 'EEE-Std#4', 'Student'),
(10, 'student5@eee.uiu.ac.bd', 'EEE-Std#5', 'Student'),
(11, 'student1@me.uiu.ac.bd', 'ME-Std-123', 'Student'),
(12, 'student2@me.uiu.ac.bd', 'ME-Std-456', 'Student'),
(13, 'student3@me.uiu.ac.bd', 'ME-Std-789', 'Student'),
(14, 'student4@me.uiu.ac.bd', 'ME-Std-321', 'Student'),
(15, 'student5@me.uiu.ac.bd', 'ME-Std-654', 'Student'),
(16, 'student1@ce.uiu.ac.bd', 'CE-Pass_1', 'Student'),
(17, 'student2@ce.uiu.ac.bd', 'CE-Pass_2', 'Student'),
(18, 'student3@ce.uiu.ac.bd', 'CE-Pass_3', 'Student'),
(19, 'student4@ce.uiu.ac.bd', 'CE-Pass_4', 'Student'),
(20, 'student5@ce.uiu.ac.bd', 'CE-Pass_5', 'Student'),
(21, 'student1@bme.uiu.ac.bd', 'BME-Secure1', 'Student'),
(22, 'student2@bme.uiu.ac.bd', 'BME-Secure2', 'Student'),
(23, 'student3@bme.uiu.ac.bd', 'BME-Secure3', 'Student'),
(24, 'student4@bme.uiu.ac.bd', 'BME-Secure4', 'Student'),
(25, 'student5@bme.uiu.ac.bd', 'BME-Secure5', 'Student'),
(26, 'student1@mse.uiu.ac.bd', 'MSE-Key#1', 'Student'),
(27, 'student2@mse.uiu.ac.bd', 'MSE-Key#2', 'Student'),
(28, 'student3@mse.uiu.ac.bd', 'MSE-Key#3', 'Student'),
(29, 'student4@mse.uiu.ac.bd', 'MSE-Key#4', 'Student'),
(30, 'student5@mse.uiu.ac.bd', 'MSE-Key#5', 'Student'),
(31, 'faculty1@cse.uiu.ac.bd', 'Prof-CSE#1', 'Faculty'),
(32, 'faculty2@cse.uiu.ac.bd', 'Prof-CSE#2', 'Faculty'),
(33, 'faculty3@cse.uiu.ac.bd', 'Prof-CSE#3', 'Faculty'),
(34, 'faculty4@cse.uiu.ac.bd', 'Prof-CSE#4', 'Faculty'),
(35, 'faculty5@cse.uiu.ac.bd', 'Prof-CSE#5', 'Faculty'),
(36, 'faculty1@eee.uiu.ac.bd', 'Prof-EEE#1', 'Faculty'),
(37, 'faculty2@eee.uiu.ac.bd', 'Prof-EEE#2', 'Faculty'),
(38, 'faculty3@eee.uiu.ac.bd', 'Prof-EEE#3', 'Faculty'),
(39, 'faculty4@eee.uiu.ac.bd', 'Prof-EEE#4', 'Faculty'),
(40, 'faculty5@eee.uiu.ac.bd', 'Prof-EEE#5', 'Faculty'),
(41, 'faculty1@me.uiu.ac.bd', 'Prof-ME-111', 'Faculty'),
(42, 'faculty2@me.uiu.ac.bd', 'Prof-ME-222', 'Faculty'),
(43, 'faculty3@me.uiu.ac.bd', 'Prof-ME-333', 'Faculty'),
(44, 'faculty4@me.uiu.ac.bd', 'Prof-ME-444', 'Faculty'),
(45, 'faculty5@me.uiu.ac.bd', 'Prof-ME-555', 'Faculty'),
(46, 'faculty1@ce.uiu.ac.bd', 'Prof-CE_01', 'Faculty'),
(47, 'faculty2@ce.uiu.ac.bd', 'Prof-CE_02', 'Faculty'),
(48, 'faculty3@ce.uiu.ac.bd', 'Prof-CE_03', 'Faculty'),
(49, 'faculty4@ce.uiu.ac.bd', 'Prof-CE_04', 'Faculty'),
(50, 'faculty5@ce.uiu.ac.bd', 'Prof-CE_05', 'Faculty'),
(51, 'faculty1@bme.uiu.ac.bd', 'Doc-BME#1', 'Faculty'),
(52, 'faculty2@bme.uiu.ac.bd', 'Doc-BME#2', 'Faculty'),
(53, 'faculty3@bme.uiu.ac.bd', 'Doc-BME#3', 'Faculty'),
(54, 'faculty4@bme.uiu.ac.bd', 'Doc-BME#4', 'Faculty'),
(55, 'faculty5@bme.uiu.ac.bd', 'Doc-BME#5', 'Faculty'),
(56, 'faculty1@mse.uiu.ac.bd', 'Doc-MSE#1', 'Faculty'),
(57, 'faculty2@mse.uiu.ac.bd', 'Doc-MSE#2', 'Faculty'),
(58, 'faculty3@mse.uiu.ac.bd', 'Doc-MSE#3', 'Faculty'),
(59, 'faculty4@mse.uiu.ac.bd', 'Doc-MSE#4', 'Faculty'),
(60, 'faculty5@mse.uiu.ac.bd', 'Doc-MSE#5', 'Faculty'),
(61, 'admin1@uiu.ac.bd', 'Root-Admin#1', 'admin'),
(62, 'admin2@uiu.ac.bd', 'Root-Admin#2', 'admin'),
(63, 'admin3@uiu.ac.bd', 'Root-Admin#3', 'admin'),
(64, 'admin4@uiu.ac.bd', 'Root-Admin#4', 'admin'),
(65, 'admin5@uiu.ac.bd', 'Root-Admin#5', 'admin');

DROP TABLE IF EXISTS `active_projects_view`;

CREATE ALGORITHM=UNDEFINED DEFINER=`root`@`localhost` SQL SECURITY DEFINER VIEW `active_projects_view` AS SELECT `research_project`.`project_id` AS `project_id`, `research_project`.`title` AS `title`, `research_project`.`status` AS `status` FROM `research_project`;

ALTER TABLE `application`
  ADD PRIMARY KEY (`project_id`,`application_id`),
  ADD KEY `idx_application_student` (`student_id`);

ALTER TABLE `faculty`
  ADD PRIMARY KEY (`faculty_id`);

ALTER TABLE `faculty_research_areas`
  ADD PRIMARY KEY (`faculty_id`,`research_area`);

ALTER TABLE `research_project`
  ADD PRIMARY KEY (`project_id`),
  ADD KEY `faculty_id` (`faculty_id`);

ALTER TABLE `student`
  ADD PRIMARY KEY (`student_id`);

ALTER TABLE `student_skills`
  ADD PRIMARY KEY (`student_id`,`skill`);

ALTER TABLE `student_interests`
  ADD PRIMARY KEY (`student_id`,`research_area`);

ALTER TABLE `user`
  ADD PRIMARY KEY (`user_id`),
  ADD UNIQUE KEY `email` (`email`);

ALTER TABLE `research_project`
  MODIFY `project_id` int(11) NOT NULL AUTO_INCREMENT, AUTO_INCREMENT=41;

ALTER TABLE `user`
  MODIFY `user_id` int(11) NOT NULL AUTO_INCREMENT;

ALTER TABLE `application`
  ADD CONSTRAINT `application_ibfk_1` FOREIGN KEY (`project_id`) REFERENCES `research_project` (`project_id`) ON DELETE CASCADE,
  ADD CONSTRAINT `application_ibfk_2` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON DELETE CASCADE;

ALTER TABLE `faculty`
  ADD CONSTRAINT `faculty_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `user` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `faculty_research_areas`
  ADD CONSTRAINT `faculty_research_areas_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE;

ALTER TABLE `research_project`
  ADD CONSTRAINT `research_project_ibfk_1` FOREIGN KEY (`faculty_id`) REFERENCES `faculty` (`faculty_id`) ON DELETE CASCADE;

ALTER TABLE `student`
  ADD CONSTRAINT `student_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `user` (`user_id`) ON DELETE CASCADE;

ALTER TABLE `student_skills`
  ADD CONSTRAINT `student_skills_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON DELETE CASCADE;

ALTER TABLE `student_interests`
  ADD CONSTRAINT `student_interests_ibfk_1` FOREIGN KEY (`student_id`) REFERENCES `student` (`student_id`) ON DELETE CASCADE;

COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;